import json
import signal
import threading
import time
from pathlib import Path

from droplet_lab.config import ExperimentConfig, OutputConfig, load_experiment
from droplet_lab.devices.camera_fake import FakeCamera
from droplet_lab.devices.function_generator_fake import FakeFunctionGenerator
from droplet_lab.devices.oscilloscope_fake import FakeOscilloscope
from droplet_lab.devices.pump_fake import FakePump
from droplet_lab.devices.scale_fake import FakeScale
from droplet_lab.displacement import (
    CalibrationCurve,
    CalibrationMeasurement,
    CalibrationModel,
    save_calibration_model,
)
from droplet_lab.orchestrator import DeviceBundle, Orchestrator, OrchestratorResult
from droplet_lab.state import ExperimentState, ExperimentStatus, StepStatus
from droplet_lab.storage import combo_folder_name


def _build_devices(state: ExperimentState, *, camera: FakeCamera | None = None) -> DeviceBundle:
    return {
        "pump": FakePump(acceleration_rpm_per_s=10000),
        "scope": FakeOscilloscope(state=state),
        "camera": camera if camera is not None else FakeCamera(),
        "function_generator": FakeFunctionGenerator(),
        "scale": FakeScale(),
    }


def _run(
    config: ExperimentConfig,
    devices: DeviceBundle,
    *,
    stop_after_s: float | None = None,
) -> OrchestratorResult:
    state = ExperimentState()
    orch = Orchestrator(config=config, devices=devices, state=state)
    if stop_after_s is not None:

        def trip() -> None:
            time.sleep(stop_after_s)
            orch.request_stop()

        threading.Thread(target=trip).start()
    return orch.run()


def _load_mini(tmp_path: Path) -> ExperimentConfig:
    cfg = load_experiment(Path("experiments/example_sweep_mini.yaml"))
    return cfg.model_copy(update={"output": OutputConfig(base_dir=tmp_path)})


class RecordingWaitOrchestrator(Orchestrator):
    def __init__(self, *args, stop_on_camera_wait: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.wait_calls: list[tuple[float, int | None]] = []
        self.stop_on_camera_wait = stop_on_camera_wait

    def _wait(self, seconds: float) -> bool:
        self.wait_calls.append((seconds, self._state.combo_index))
        if seconds == self._cfg.timing.wait_time_camera and self.stop_on_camera_wait:
            self.request_stop()
            return True
        return False


def _with_camera_wait(
    cfg: ExperimentConfig,
    *,
    wait_time_camera: float,
    combos: int,
) -> ExperimentConfig:
    return cfg.model_copy(
        update={
            "sweep": cfg.sweep.model_copy(
                update={
                    "amplitudes_vpp": [3.0, 5.0][:combos],
                    "hold_s": 0.05,
                }
            ),
            "timing": cfg.timing.model_copy(
                update={
                    "stabilization_rpm_change_s": 0.0,
                    "stabilization_freq_change_s": 0.0,
                    "stabilization_amp_change_s": 0.0,
                    "image_interval_s": 1.0,
                    "camera_latency_tolerance_s": 0.0,
                    "wait_time_camera": wait_time_camera,
                }
            ),
        }
    )


def test_single_combination_completes(minimal_config: ExperimentConfig) -> None:
    state = ExperimentState()
    devices = _build_devices(state)
    result = Orchestrator(config=minimal_config, devices=devices, state=state).run()

    assert result.status is ExperimentStatus.COMPLETED
    exp = result.experiment_dir.root
    assert (exp / "experiment.json").exists()
    assert (exp / "runs.csv").exists()
    # scale disabled — no scale.csv
    assert not (exp / "scale.csv").exists()
    # Per-combo files live inside the combo folder, NOT at root.
    assert not (exp / "pump.csv").exists()
    assert not (exp / "oscilloscope.csv").exists()

    combos = sorted((exp / "steps").iterdir())
    assert len(combos) == 1
    for combo in combos:
        assert (combo / "pump.csv").exists(), combo
        assert (combo / "oscilloscope.csv").exists(), combo
        meta = json.loads((combo / "step.json").read_text())
        assert meta["experiment_id"] == minimal_config.experiment_id
        assert meta["nozzle_id"] == minimal_config.nozzle_id
        assert meta["vibrometer_factor_um_per_v"] == minimal_config.vibrometer.factor_um_per_v
        assert meta["status"] in {
            StepStatus.COMPLETED.value,
            StepStatus.COMPLETED_NO_IMAGING.value,
        }
        assert (combo / "images").exists()


def test_ctrl_c_aborts_cleanly(minimal_config: ExperimentConfig) -> None:
    state = ExperimentState()
    devices = _build_devices(state)
    result = _run(minimal_config, devices, stop_after_s=0.05)
    assert result.status is ExperimentStatus.ABORTED


def test_installed_sigint_handler_aborts_run(minimal_config: ExperimentConfig) -> None:
    class InterruptingCamera(FakeCamera):
        def trigger_capture(self) -> None:
            signal.raise_signal(signal.SIGINT)

    previous_handler = signal.getsignal(signal.SIGINT)
    state = ExperimentState()
    devices = _build_devices(state, camera=InterruptingCamera())

    result = Orchestrator(
        config=minimal_config,
        devices=devices,
        state=state,
        install_signal_handler=True,
    ).run()

    assert result.status is ExperimentStatus.ABORTED
    assert result.failure_reason == "interrupted by Ctrl-C"
    assert signal.getsignal(signal.SIGINT) is previous_handler


def test_camera_failure_marks_experiment_failed(minimal_config: ExperimentConfig) -> None:
    state = ExperimentState()
    cam = FakeCamera(fail_after_triggers=1)
    devices = _build_devices(state, camera=cam)
    result = Orchestrator(config=minimal_config, devices=devices, state=state).run()

    assert result.status is ExperimentStatus.FAILED
    combos = sorted((result.experiment_dir.root / "steps").iterdir())
    failed = [
        c
        for c in combos
        if json.loads((c / "step.json").read_text())["status"] == StepStatus.CAMERA_FAILED.value
    ]
    assert len(failed) >= 1


def test_wait_time_camera_runs_between_completed_combos(
    minimal_config: ExperimentConfig,
) -> None:
    cfg = _with_camera_wait(minimal_config, wait_time_camera=2.0, combos=2)
    state = ExperimentState()
    orch = RecordingWaitOrchestrator(config=cfg, devices=_build_devices(state), state=state)

    result = orch.run()

    assert result.status is ExperimentStatus.COMPLETED
    camera_waits = [call for call in orch.wait_calls if call[0] == 2.0]
    assert camera_waits == [(2.0, 1)]


def test_wait_time_camera_does_not_run_after_final_combo(
    minimal_config: ExperimentConfig,
) -> None:
    cfg = _with_camera_wait(minimal_config, wait_time_camera=2.0, combos=1)
    state = ExperimentState()
    orch = RecordingWaitOrchestrator(config=cfg, devices=_build_devices(state), state=state)

    result = orch.run()

    assert result.status is ExperimentStatus.COMPLETED
    assert [call for call in orch.wait_calls if call[0] == 2.0] == []


def test_stop_during_wait_time_camera_aborts_current_combo(
    minimal_config: ExperimentConfig,
) -> None:
    cfg = _with_camera_wait(minimal_config, wait_time_camera=2.0, combos=2)
    state = ExperimentState()
    orch = RecordingWaitOrchestrator(
        config=cfg,
        devices=_build_devices(state),
        state=state,
        stop_on_camera_wait=True,
    )

    result = orch.run()

    assert result.status is ExperimentStatus.ABORTED
    rows = (result.experiment_dir.root / "runs.csv").read_text().splitlines()[1:]
    assert len(rows) == 1
    assert ";aborted;" in rows[0]
    step_meta = json.loads(
        (
            result.experiment_dir.root / "steps" / "combo_001_rpm0200_f20Hz_amp3V" / "step.json"
        ).read_text()
    )
    assert step_meta["status"] == StepStatus.ABORTED.value


def test_scale_enabled_writes_scale_csv_with_initial_row(minimal_config: ExperimentConfig) -> None:
    cfg = minimal_config.model_copy(
        update={
            "devices": minimal_config.devices.model_copy(
                update={
                    "scale": minimal_config.devices.scale.model_copy(
                        update={"enabled": True, "port": "COM5", "interval_s": 0.1}
                    )
                }
            )
        }
    )
    state = ExperimentState()
    devices = _build_devices(state)
    result = Orchestrator(config=cfg, devices=devices, state=state).run()
    scale_csv = result.experiment_dir.root / "scale.csv"
    assert scale_csv.exists()
    lines = scale_csv.read_text().splitlines()
    assert "phase" in lines[0]
    # First data row must be the initial pre-pump weight.
    assert lines[1].split(";")[2] == "initial"
    # Subsequent rows are phase=sweep (if any were captured before stop).
    if len(lines) > 2:
        assert any(line.split(";")[2] == "sweep" for line in lines[2:])

    payload = json.loads((result.experiment_dir.root / "experiment.json").read_text())
    assert payload["status"] == "completed"
    assert payload["initial_weight_g"] is not None


def test_full_sweep_writes_eight_combos_in_order(tmp_path: Path) -> None:
    base_cfg = _load_mini(tmp_path)
    cfg = base_cfg.model_copy(
        update={
            "sweep": base_cfg.sweep.model_copy(update={"hold_s": 0.05}),
            "timing": base_cfg.timing.model_copy(
                update={
                    "stabilization_rpm_change_s": 0.0,
                    "stabilization_freq_change_s": 0.0,
                    "stabilization_amp_change_s": 0.0,
                    "image_interval_s": 1.0,
                    "camera_latency_tolerance_s": 0.0,
                    "wait_time_camera": 0.0,
                }
            ),
        }
    )
    state = ExperimentState()
    fake_fg = FakeFunctionGenerator()
    devices: DeviceBundle = {
        "pump": FakePump(acceleration_rpm_per_s=10000),
        "scope": FakeOscilloscope(state=state),
        "camera": FakeCamera(),
        "function_generator": fake_fg,
        "scale": FakeScale(),
    }
    result = Orchestrator(config=cfg, devices=devices, state=state).run()
    assert result.status is ExperimentStatus.COMPLETED, result.failure_reason

    root = result.experiment_dir.root
    names = sorted(c.name for c in (root / "steps").iterdir())
    assert names == [
        "combo_001_rpm1125_f5Hz_amp2V",
        "combo_002_rpm1125_f5Hz_amp4V",
        "combo_003_rpm1125_f5.5Hz_amp2V",
        "combo_004_rpm1125_f5.5Hz_amp4V",
        "combo_005_rpm1175_f5Hz_amp2V",
        "combo_006_rpm1175_f5Hz_amp4V",
        "combo_007_rpm1175_f5.5Hz_amp2V",
        "combo_008_rpm1175_f5.5Hz_amp4V",
    ]
    for folder in (root / "steps").iterdir():
        assert (folder / "step.json").exists()
        assert (folder / "pump.csv").exists(), folder
        assert (folder / "oscilloscope.csv").exists(), folder
        assert (folder / "images").is_dir()

    # runs.csv: header + 8 rows, all completed.
    runs_lines = (root / "runs.csv").read_text().splitlines()
    assert runs_lines[0].startswith("timestamp_utc;")
    assert len(runs_lines) == 9
    for line in runs_lines[1:]:
        assert ";completed;" in line, line

    # scale.csv has initial row + sweep rows.
    scale_lines = (root / "scale.csv").read_text().splitlines()
    assert scale_lines[1].split(";")[2] == "initial"
    assert any(line.split(";")[2] == "sweep" for line in scale_lines[2:])

    # Function generator received the expected (freq, amp) sequence.
    # Track only the meaningful state-setting calls in order.
    keep = {"set_frequency_hz", "set_amplitude_vpp", "enable_output"}
    trimmed = [c for c in fake_fg.calls if c[0] in keep]
    # Drop any leading enable_output(False) from __enter__ + safe defaults setup.
    idx = trimmed.index(("set_frequency_hz", 5.0))
    expected = [
        ("set_frequency_hz", 5.0),
        ("set_amplitude_vpp", 2.0),
        ("enable_output", True),
        ("set_amplitude_vpp", 4.0),
        ("set_frequency_hz", 5.5),
        ("set_amplitude_vpp", 2.0),
        ("set_amplitude_vpp", 4.0),
        ("set_frequency_hz", 5.0),
        ("set_amplitude_vpp", 2.0),
        ("set_amplitude_vpp", 4.0),
        ("set_frequency_hz", 5.5),
        ("set_amplitude_vpp", 2.0),
        ("set_amplitude_vpp", 4.0),
    ]
    assert trimmed[idx : idx + len(expected)] == expected

    # experiment.json
    payload = json.loads((root / "experiment.json").read_text())
    assert payload["status"] == "completed"
    assert payload["initial_weight_g"] is not None


def test_randomized_sweep_executes_shuffled_order_with_same_folder_names(
    minimal_config: ExperimentConfig,
) -> None:
    cfg = minimal_config.model_copy(
        update={
            "sweep": minimal_config.sweep.model_copy(
                update={
                    "speeds_rpm": [200, 800],
                    "frequencies_hz": [20.0, 25.0],
                    "amplitudes_vpp": [3.0, 5.0],
                    "hold_s": 0.2,
                    "random": True,
                }
            )
        }
    )
    state = ExperimentState()
    devices = _build_devices(state)

    result = Orchestrator(config=cfg, devices=devices, state=state).run()

    assert result.status is ExperimentStatus.COMPLETED, result.failure_reason
    root = result.experiment_dir.root
    assert sorted(c.name for c in (root / "steps").iterdir()) == [
        "combo_001_rpm0200_f20Hz_amp3V",
        "combo_002_rpm0200_f20Hz_amp5V",
        "combo_003_rpm0200_f25Hz_amp3V",
        "combo_004_rpm0200_f25Hz_amp5V",
        "combo_005_rpm0800_f20Hz_amp3V",
        "combo_006_rpm0800_f20Hz_amp5V",
        "combo_007_rpm0800_f25Hz_amp3V",
        "combo_008_rpm0800_f25Hz_amp5V",
    ]

    rows = (root / "runs.csv").read_text().splitlines()[1:]
    assert [int(row.split(";")[1]) for row in rows] == [5, 2, 6, 3, 1, 4, 8, 7]
    assert [row.split(";")[8].replace("\\", "/") for row in rows] == [
        "steps/combo_005_rpm0800_f20Hz_amp3V",
        "steps/combo_002_rpm0200_f20Hz_amp5V",
        "steps/combo_006_rpm0800_f20Hz_amp5V",
        "steps/combo_003_rpm0200_f25Hz_amp3V",
        "steps/combo_001_rpm0200_f20Hz_amp3V",
        "steps/combo_004_rpm0200_f25Hz_amp5V",
        "steps/combo_008_rpm0800_f25Hz_amp5V",
        "steps/combo_007_rpm0800_f25Hz_amp3V",
    ]


def test_displacement_sweep_resolves_voltage_and_records_target(
    minimal_config: ExperimentConfig,
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "model.json"
    save_calibration_model(
        CalibrationModel(
            version=1,
            created_at_utc="2026-06-19T00:00:00Z",
            vibrometer_factor_um_per_v=minimal_config.vibrometer.factor_um_per_v,
            amplifier_gain=2.0,
            curves=[
                CalibrationCurve(
                    frequency_hz=20.0,
                    safe_max_amplitude_vpp=5.0,
                    measurements=[
                        CalibrationMeasurement(1.0, 1.0, 1000.0, [1000.0]),
                        CalibrationMeasurement(3.0, 3.0, 3000.0, [3000.0]),
                    ],
                )
            ],
        ),
        model_path,
    )
    cfg = minimal_config.model_copy(
        update={
            "sweep": minimal_config.sweep.model_copy(
                update={
                    "amplitudes_vpp": None,
                    "displacements_um": [2000.0],
                    "hold_s": 0.1,
                }
            ),
            "displacement": minimal_config.displacement.model_copy(
                update={"model_path": model_path}
            ),
        }
    )
    state = ExperimentState()
    fake_fg = FakeFunctionGenerator()
    devices = _build_devices(state)
    devices["function_generator"] = fake_fg

    result = Orchestrator(config=cfg, devices=devices, state=state).run()

    assert result.status is ExperimentStatus.COMPLETED, result.failure_reason
    assert ("set_amplitude_vpp", 2.0) in fake_fg.calls
    step = next((result.experiment_dir.root / "steps").iterdir())
    meta = json.loads((step / "step.json").read_text())
    assert meta["target_displacement_um"] == 2000.0
    assert meta["set_amplitude_vpp"] == 2.0
    runs_row = (result.experiment_dir.root / "runs.csv").read_text().splitlines()[1]
    assert runs_row.endswith(";2000.0")


def test_combo_folder_exists_before_state_advances(
    minimal_config: ExperimentConfig, tmp_path: Path
) -> None:
    class FolderGuardState(ExperimentState):
        def update(
            self,
            *,
            combo_index: int,
            set_speed_rpm: int,
            set_frequency_hz: float,
            set_amplitude_vpp: float,
            target_displacement_um: float | None = None,
        ) -> None:
            if combo_index > 1:
                expected = combo_folder_name(
                    combo_index, set_speed_rpm, set_frequency_hz, set_amplitude_vpp
                )
                assert any(tmp_path.glob(f"*/steps/{expected}"))
            super().update(
                combo_index=combo_index,
                set_speed_rpm=set_speed_rpm,
                set_frequency_hz=set_frequency_hz,
                set_amplitude_vpp=set_amplitude_vpp,
                target_displacement_um=target_displacement_um,
            )

    cfg = minimal_config.model_copy(
        update={
            "sweep": minimal_config.sweep.model_copy(
                update={"amplitudes_vpp": [3.0, 5.0], "hold_s": 0.2}
            )
        }
    )
    state = FolderGuardState()
    devices = _build_devices(state)

    result = Orchestrator(config=cfg, devices=devices, state=state).run()

    assert result.status is ExperimentStatus.COMPLETED, result.failure_reason
