"""Experiment orchestrator.

Owns the lifecycle of one experiment run:

* Build the ``ExperimentDirectory``, persist ``experiment.json``.
* Read an initial scale weight (if enabled) before any worker starts.
* Spawn ``PumpWorker`` / ``ScopeWorker`` (and optional ``ScaleWorker``).
* Walk the sweep cross-product (rpm x freq x amp), driving the function
  generator directly, signalling speed changes via the pump command queue,
  running camera capture, and appending one ``runs.csv`` row per combo.
* Watch for ``error_event`` / ``stop_event`` and shut down deterministically.
"""

from __future__ import annotations

import queue
import signal
import threading
import time
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from loguru import logger

from droplet_lab.config import ExperimentConfig
from droplet_lab.devices.base import (
    Camera,
    FunctionGenerator,
    Oscilloscope,
    Pump,
    Scale,
)
from droplet_lab.logging_setup import setup_logging
from droplet_lab.state import (
    CameraStatus,
    ExperimentState,
    ExperimentStatus,
    StepStatus,
)
from droplet_lab.storage import (
    ExperimentDirectory,
    RunsRow,
    ScaleRow,
    utc_now_iso,
)
from droplet_lab.sweep import ChangedKind, SweepCombination, expand_sweep
from droplet_lab.workers.camera_worker import (
    CameraResult,
    CameraResultStatus,
    run_camera_capture,
)
from droplet_lab.workers.pump_worker import PumpWorker, SetSpeedCommand
from droplet_lab.workers.scale_worker import ScaleWorker
from droplet_lab.workers.scope_worker import ScopeWorker


class DeviceBundle(TypedDict):
    pump: Pump
    scope: Oscilloscope
    camera: Camera
    function_generator: FunctionGenerator
    scale: Scale


@dataclass(frozen=True, slots=True)
class OrchestratorResult:
    status: ExperimentStatus
    experiment_dir: ExperimentDirectory
    failure_reason: str | None = None


_PUMP_LOG_INTERVAL_S = 5.0
_SCOPE_LOG_INTERVAL_S = 15.0


class Orchestrator:
    def __init__(
        self,
        *,
        config: ExperimentConfig,
        devices: DeviceBundle,
        state: ExperimentState,
        install_signal_handler: bool = False,
    ) -> None:
        self._cfg = config
        self._devices = devices
        self._state = state
        self._stop = threading.Event()
        self._error = threading.Event()
        self._install_signal_handler = install_signal_handler
        self._log = logger.bind(component="orchestrator")
        self._initial_weight_g: float | None = None

    def request_stop(self) -> None:
        self._stop.set()

    def run(self) -> OrchestratorResult:
        exp = ExperimentDirectory.create(
            base_dir=self._cfg.output.base_dir,
            experiment_id=self._cfg.experiment_id,
        )
        setup_logging(exp.root)
        self._log.info("experiment dir: {}", exp.root)
        self._write_experiment_json(exp, status=ExperimentStatus.RUNNING)

        if self._install_signal_handler:
            signal.signal(signal.SIGINT, lambda *_: self._stop.set())

        result_status = ExperimentStatus.RUNNING
        failure_reason: str | None = None
        cmd_q: queue.Queue[SetSpeedCommand] = queue.Queue()

        try:
            with ExitStack() as stack:
                pump = stack.enter_context(self._devices["pump"])
                scope = stack.enter_context(self._devices["scope"])
                fg = stack.enter_context(self._devices["function_generator"])
                stack.enter_context(self._devices["camera"])
                scale_cm = (
                    stack.enter_context(self._devices["scale"])
                    if self._cfg.devices.scale.enabled
                    else None
                )

                if scale_cm is not None:
                    self._initial_weight_g = scale_cm.read_weight_g()
                    exp.append_scale_row(
                        ScaleRow(
                            timestamp_utc=utc_now_iso(),
                            elapsed_s=0.0,
                            phase="initial",
                            combo_index=None,
                            set_speed_rpm=None,
                            set_frequency_hz=None,
                            set_amplitude_vpp=None,
                            weight_g=self._initial_weight_g,
                        )
                    )
                    self._write_experiment_json(exp, status=ExperimentStatus.RUNNING)
                    self._log.info("initial weight: {} g", self._initial_weight_g)

                # Belt-and-suspenders: PSG9080.__enter__ also does this, but if a non-PSG9080
                # driver is in the bundle the orchestrator must enforce the safe-defaults itself.
                fg.set_sine()
                fg.enable_output(False)

                combos = expand_sweep(
                    speeds_rpm=list(self._cfg.sweep.speeds_rpm),
                    frequencies_hz=list(self._cfg.sweep.frequencies_hz),
                    amplitudes_vpp=list(self._cfg.sweep.amplitudes_vpp),
                    hold_s=self._cfg.sweep.hold_s,
                )
                first = combos[0]
                self._state.update(
                    combo_index=first.combo_index,
                    set_speed_rpm=first.set_speed_rpm,
                    set_frequency_hz=first.frequency_hz,
                    set_amplitude_vpp=first.amplitude_vpp,
                )
                first_folder = exp.create_combo_folder(first)

                pump_worker = PumpWorker(
                    pump=pump,
                    state=self._state,
                    command_queue=cmd_q,
                    stop_event=self._stop,
                    error_event=self._error,
                    log_interval_s=_PUMP_LOG_INTERVAL_S,
                    experiment_dir=exp,
                )
                scope_worker = ScopeWorker(
                    scope=scope,
                    state=self._state,
                    stop_event=self._stop,
                    error_event=self._error,
                    log_interval_s=_SCOPE_LOG_INTERVAL_S,
                    vibrometer_factor_um_per_v=self._cfg.vibrometer.factor_um_per_v,
                    experiment_dir=exp,
                )
                pump_thread = threading.Thread(target=pump_worker.run, name="pump")
                scope_thread = threading.Thread(target=scope_worker.run, name="scope")
                pump_thread.start()
                scope_thread.start()

                scale_thread: threading.Thread | None = None
                if scale_cm is not None:
                    scale_worker = ScaleWorker(
                        scale=scale_cm,
                        state=self._state,
                        stop_event=self._stop,
                        error_event=self._error,
                        log_interval_s=self._cfg.devices.scale.interval_s,
                        experiment_dir=exp,
                    )
                    scale_thread = threading.Thread(target=scale_worker.run, name="scale")
                    scale_thread.start()

                result_status, failure_reason = self._walk_sweep(
                    exp=exp,
                    combos=combos,
                    first_folder=first_folder,
                    cmd_q=cmd_q,
                    camera=self._devices["camera"],
                    fg=fg,
                )

                self._stop.set()
                pump_thread.join(timeout=10.0)
                scope_thread.join(timeout=10.0)
                if scale_thread is not None:
                    scale_thread.join(timeout=10.0)

                if self._error.is_set() and result_status is ExperimentStatus.COMPLETED:
                    result_status = ExperimentStatus.FAILED
                    failure_reason = failure_reason or "worker thread reported error"

        except Exception as e:
            self._log.exception("orchestrator crashed")
            result_status = ExperimentStatus.FAILED
            failure_reason = str(e)

        self._write_experiment_json(exp, status=result_status, failure_reason=failure_reason)
        return OrchestratorResult(
            status=result_status,
            experiment_dir=exp,
            failure_reason=failure_reason,
        )

    def _walk_sweep(
        self,
        *,
        exp: ExperimentDirectory,
        combos: list[SweepCombination],
        first_folder: Path,
        cmd_q: queue.Queue[SetSpeedCommand],
        camera: Camera,
        fg: FunctionGenerator,
    ) -> tuple[ExperimentStatus, str | None]:
        for combo in combos:
            if self._stop.is_set() or self._error.is_set():
                return self._final_status_after_break(), None

            if combo.combo_index > 1:
                self._state.update(
                    combo_index=combo.combo_index,
                    set_speed_rpm=combo.set_speed_rpm,
                    set_frequency_hz=combo.frequency_hz,
                    set_amplitude_vpp=combo.amplitude_vpp,
                )

            if combo.changed in ("initial", "rpm"):
                cmd_q.put(SetSpeedCommand(rpm=combo.set_speed_rpm))

            if combo.changed in ("initial", "rpm", "freq"):
                fg.set_frequency_hz(combo.frequency_hz)
            fg.set_amplitude_vpp(combo.amplitude_vpp)
            if combo.combo_index == 1:
                fg.enable_output(True)

            step_folder = first_folder if combo.combo_index == 1 else exp.create_combo_folder(combo)
            step_meta = self._initial_step_meta(combo)
            self._write_step_json(step_folder, step_meta)

            stabilization = self._stabilization_for(combo.changed)
            self._log.info(
                "combo {} rpm={} freq={}Hz amp={}Vpp changed={} - stabilizing {}s",
                combo.combo_index,
                combo.set_speed_rpm,
                combo.frequency_hz,
                combo.amplitude_vpp,
                combo.changed,
                stabilization,
            )
            step_meta["status"] = StepStatus.STABILIZING.value
            self._write_step_json(step_folder, step_meta)

            if self._wait(stabilization):
                step_meta["status"] = StepStatus.ABORTED.value
                step_meta["end_time_utc"] = utc_now_iso()
                self._write_step_json(step_folder, step_meta)
                self._append_runs_row(exp, combo, step_folder, step_meta, "aborted", None)
                return self._final_status_after_break(), None

            imaging_duration = max(0.0, combo.hold_s - stabilization)
            step_meta["status"] = StepStatus.IMAGING.value
            step_meta["imaging_planned_s"] = imaging_duration
            self._write_step_json(step_folder, step_meta)

            result: CameraResult = run_camera_capture(
                camera=camera,
                output_folder=step_folder / "images",
                interval_s=self._cfg.timing.image_interval_s,
                duration_s=imaging_duration,
                latency_tolerance_s=self._cfg.timing.camera_latency_tolerance_s,
                stop_event=self._stop,
            )
            step_meta["captures"] = result.captures
            step_meta["end_time_utc"] = utc_now_iso()

            match result.status:
                case CameraResultStatus.COMPLETED:
                    step_meta["status"] = StepStatus.COMPLETED.value
                    step_meta["camera_status"] = CameraStatus.COMPLETED.value
                    self._write_step_json(step_folder, step_meta)
                    self._append_runs_row(exp, combo, step_folder, step_meta, "completed", None)
                case CameraResultStatus.NO_IMAGING:
                    step_meta["status"] = StepStatus.COMPLETED_NO_IMAGING.value
                    step_meta["camera_status"] = CameraStatus.NOT_STARTED.value
                    self._write_step_json(step_folder, step_meta)
                    self._append_runs_row(
                        exp, combo, step_folder, step_meta, "completed_no_imaging", None
                    )
                case CameraResultStatus.ABORTED:
                    step_meta["status"] = StepStatus.ABORTED.value
                    step_meta["camera_status"] = CameraStatus.ABORTED.value
                    self._write_step_json(step_folder, step_meta)
                    self._append_runs_row(exp, combo, step_folder, step_meta, "aborted", None)
                    return self._final_status_after_break(), None
                case CameraResultStatus.FAILED:
                    step_meta["status"] = StepStatus.CAMERA_FAILED.value
                    step_meta["camera_status"] = CameraStatus.FAILED.value
                    step_meta["camera_error"] = result.error
                    self._write_step_json(step_folder, step_meta)
                    self._append_runs_row(
                        exp, combo, step_folder, step_meta, "camera_failed", result.error
                    )
                    return ExperimentStatus.FAILED, f"camera failed at combo {combo.combo_index}"

        return ExperimentStatus.COMPLETED, None

    def _wait(self, seconds: float) -> bool:
        """Cooperative wait. Returns True if stop_event/error_event tripped."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self._stop.is_set() or self._error.is_set():
                return True
            time.sleep(0.05)
        return False

    def _final_status_after_break(self) -> ExperimentStatus:
        if self._error.is_set():
            return ExperimentStatus.FAILED
        return ExperimentStatus.ABORTED

    def _stabilization_for(self, changed: ChangedKind) -> float:
        t = self._cfg.timing
        if changed in ("initial", "rpm"):
            return t.stabilization_rpm_change_s
        if changed == "freq":
            return t.stabilization_freq_change_s
        return t.stabilization_amp_change_s

    def _initial_step_meta(self, combo: SweepCombination) -> dict[str, Any]:
        return {
            "combo_index": combo.combo_index,
            "set_speed_rpm": combo.set_speed_rpm,
            "set_frequency_hz": combo.frequency_hz,
            "set_amplitude_vpp": combo.amplitude_vpp,
            "changed": combo.changed,
            "hold_s": combo.hold_s,
            "stabilization_s": self._stabilization_for(combo.changed),
            "image_interval_s": self._cfg.timing.image_interval_s,
            "camera_latency_tolerance_s": self._cfg.timing.camera_latency_tolerance_s,
            "start_time_utc": utc_now_iso(),
            "status": StepStatus.PLANNED.value,
            "camera_status": CameraStatus.NOT_STARTED.value,
            "captures": 0,
            "pump_csv": "pump.csv",
            "oscilloscope_csv": "oscilloscope.csv",
            "scale_csv": "../../scale.csv" if self._cfg.devices.scale.enabled else None,
        }

    def _write_step_json(self, folder: Path, payload: dict[str, Any]) -> None:
        ExperimentDirectory.write_json(folder / "step.json", payload)

    def _append_runs_row(
        self,
        exp: ExperimentDirectory,
        combo: SweepCombination,
        step_folder: Path,
        step_meta: dict[str, Any],
        status: str,
        failure_reason: str | None,
    ) -> None:
        exp.append_runs_row(
            RunsRow(
                timestamp_utc=utc_now_iso(),
                combo_index=combo.combo_index,
                experiment_id=self._cfg.experiment_id,
                nozzle_id=self._cfg.nozzle_id,
                set_speed_rpm=combo.set_speed_rpm,
                set_frequency_hz=combo.frequency_hz,
                set_amplitude_vpp=combo.amplitude_vpp,
                hold_s=combo.hold_s,
                step_folder=str(step_folder.relative_to(exp.root)),
                status=status,
                n_captures=int(step_meta.get("captures", 0)),
                failure_reason=failure_reason,
            )
        )

    def _write_experiment_json(
        self,
        exp: ExperimentDirectory,
        *,
        status: ExperimentStatus,
        failure_reason: str | None = None,
    ) -> None:
        payload = self._cfg.model_dump(mode="json")
        payload["status"] = status.value
        payload["failure_reason"] = failure_reason
        payload["initial_weight_g"] = self._initial_weight_g
        payload["written_at_utc"] = utc_now_iso()
        ExperimentDirectory.write_json(exp.root / "experiment.json", payload)
