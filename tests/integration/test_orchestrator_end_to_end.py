import json
import threading
import time
from pathlib import Path

from droplet_lab.config import ExperimentConfig, OutputConfig, load_experiment
from droplet_lab.devices.camera_fake import FakeCamera
from droplet_lab.devices.function_generator_fake import FakeFunctionGenerator
from droplet_lab.devices.oscilloscope_fake import FakeOscilloscope
from droplet_lab.devices.pump_fake import FakePump
from droplet_lab.devices.scale_fake import FakeScale
from droplet_lab.orchestrator import DeviceBundle, Orchestrator, OrchestratorResult
from droplet_lab.state import ExperimentState, ExperimentStatus, StepStatus


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
    cfg = _load_mini(tmp_path)
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
        "combo_001_rpm0200_f20Hz_amp3V",
        "combo_002_rpm0200_f20Hz_amp5V",
        "combo_003_rpm0200_f25Hz_amp3V",
        "combo_004_rpm0200_f25Hz_amp5V",
        "combo_005_rpm0300_f20Hz_amp3V",
        "combo_006_rpm0300_f20Hz_amp5V",
        "combo_007_rpm0300_f25Hz_amp3V",
        "combo_008_rpm0300_f25Hz_amp5V",
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
    idx = trimmed.index(("set_frequency_hz", 20.0))
    expected = [
        ("set_frequency_hz", 20.0),
        ("set_amplitude_vpp", 3.0),
        ("enable_output", True),
        ("set_amplitude_vpp", 5.0),
        ("set_frequency_hz", 25.0),
        ("set_amplitude_vpp", 3.0),
        ("set_amplitude_vpp", 5.0),
        ("set_frequency_hz", 20.0),
        ("set_amplitude_vpp", 3.0),
        ("set_amplitude_vpp", 5.0),
        ("set_frequency_hz", 25.0),
        ("set_amplitude_vpp", 3.0),
        ("set_amplitude_vpp", 5.0),
    ]
    assert trimmed[idx : idx + len(expected)] == expected

    # experiment.json
    payload = json.loads((root / "experiment.json").read_text())
    assert payload["status"] == "completed"
    assert payload["initial_weight_g"] is not None
