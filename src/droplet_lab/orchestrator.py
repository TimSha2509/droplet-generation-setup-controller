"""Experiment orchestrator.

Owns the lifecycle of one experiment run:

* Build the ``ExperimentDirectory``, persist ``experiment.json``.
* Spawn ``PumpWorker`` / ``ScopeWorker`` (and optional ``ScaleWorker``) threads.
* Walk the ramp profile, signalling speed changes and per-step camera capture.
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
from droplet_lab.devices.base import Camera, Oscilloscope, Pump, Scale
from droplet_lab.logging_setup import setup_logging
from droplet_lab.state import (
    CameraStatus,
    ExperimentState,
    ExperimentStatus,
    StepStatus,
)
from droplet_lab.storage import ExperimentDirectory, utc_now_iso
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
    scale: Scale


@dataclass(frozen=True, slots=True)
class OrchestratorResult:
    status: ExperimentStatus
    experiment_dir: ExperimentDirectory
    failure_reason: str | None = None


_PUMP_LOG_INTERVAL_S = 5.0
_SCOPE_LOG_INTERVAL_S = 15.0
_SCALE_LOG_INTERVAL_S = 1.0


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
                stack.enter_context(self._devices["camera"])
                scale_cm = (
                    stack.enter_context(self._devices["scale"])
                    if self._cfg.devices.scale.enabled
                    else None
                )

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
                    vibrometer_factor_um_per_v=self._cfg.actuation.vibrometer_factor_um_per_v,
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
                        log_interval_s=_SCALE_LOG_INTERVAL_S,
                        experiment_dir=exp,
                    )
                    scale_thread = threading.Thread(target=scale_worker.run, name="scale")
                    scale_thread.start()

                result_status, failure_reason = self._walk_ramp(
                    exp=exp,
                    cmd_q=cmd_q,
                    camera=self._devices["camera"],
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

    def _walk_ramp(
        self,
        *,
        exp: ExperimentDirectory,
        cmd_q: queue.Queue[SetSpeedCommand],
        camera: Camera,
    ) -> tuple[ExperimentStatus, str | None]:
        # Initial speed via cmd_q so PumpWorker logs it
        first = self._cfg.ramp[0]
        cmd_q.put(SetSpeedCommand(rpm=first.speed_rpm))

        for step_index, step in enumerate(self._cfg.ramp, start=1):
            if self._stop.is_set() or self._error.is_set():
                return self._final_status_after_break(), None

            self._state.update(step_index=step_index, set_speed_rpm=step.speed_rpm)

            if step_index > 1:
                cmd_q.put(SetSpeedCommand(rpm=step.speed_rpm))

            step_folder = exp.create_step_folder(
                step_index=step_index,
                set_speed_rpm=step.speed_rpm,
            )
            step_meta = self._initial_step_meta(step_index, step.speed_rpm, step.hold_s)
            self._write_step_json(step_folder, step_meta)

            self._log.info("step {} @ {} rpm — stabilizing", step_index, step.speed_rpm)
            step_meta["status"] = StepStatus.STABILIZING.value
            self._write_step_json(step_folder, step_meta)

            if self._wait(self._cfg.timing.stabilization_s):
                step_meta["status"] = StepStatus.ABORTED.value
                step_meta["end_time_utc"] = utc_now_iso()
                self._write_step_json(step_folder, step_meta)
                return self._final_status_after_break(), None

            imaging_duration = max(0.0, step.hold_s - self._cfg.timing.stabilization_s)
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
                case CameraResultStatus.NO_IMAGING:
                    step_meta["status"] = StepStatus.COMPLETED_NO_IMAGING.value
                    step_meta["camera_status"] = CameraStatus.NOT_STARTED.value
                case CameraResultStatus.ABORTED:
                    step_meta["status"] = StepStatus.ABORTED.value
                    step_meta["camera_status"] = CameraStatus.ABORTED.value
                    self._write_step_json(step_folder, step_meta)
                    return self._final_status_after_break(), None
                case CameraResultStatus.FAILED:
                    step_meta["status"] = StepStatus.CAMERA_FAILED.value
                    step_meta["camera_status"] = CameraStatus.FAILED.value
                    step_meta["camera_error"] = result.error
                    self._write_step_json(step_folder, step_meta)
                    return ExperimentStatus.FAILED, f"camera failed at step {step_index}"

            self._write_step_json(step_folder, step_meta)

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

    def _initial_step_meta(self, step_index: int, rpm: int, hold_s: float) -> dict[str, Any]:
        return {
            "step_index": step_index,
            "set_speed_rpm": rpm,
            "hold_s": hold_s,
            "stabilization_s": self._cfg.timing.stabilization_s,
            "image_interval_s": self._cfg.timing.image_interval_s,
            "camera_latency_tolerance_s": self._cfg.timing.camera_latency_tolerance_s,
            "start_time_utc": utc_now_iso(),
            "status": StepStatus.PLANNED.value,
            "camera_status": CameraStatus.NOT_STARTED.value,
            "captures": 0,
        }

    def _write_step_json(self, folder: Path, payload: dict[str, Any]) -> None:
        ExperimentDirectory.write_json(folder / "step.json", payload)

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
        payload["written_at_utc"] = utc_now_iso()
        ExperimentDirectory.write_json(exp.root / "experiment.json", payload)
