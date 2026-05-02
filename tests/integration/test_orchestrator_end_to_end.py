import json
import threading
import time

from droplet_lab.config import ExperimentConfig
from droplet_lab.devices.camera_fake import FakeCamera
from droplet_lab.devices.oscilloscope_fake import FakeOscilloscope
from droplet_lab.devices.pump_fake import FakePump
from droplet_lab.devices.scale_fake import FakeScale
from droplet_lab.orchestrator import DeviceBundle, Orchestrator, OrchestratorResult
from droplet_lab.state import ExperimentState, ExperimentStatus, StepStatus


def _build_devices(state: ExperimentState, *, camera: FakeCamera | None = None) -> DeviceBundle:
    devices: DeviceBundle = {
        "pump": FakePump(acceleration_rpm_per_s=10000),
        "scope": FakeOscilloscope(state=state),
        "camera": camera if camera is not None else FakeCamera(),
        "scale": FakeScale(),
    }
    return devices


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


def test_full_ramp_completes(minimal_config: ExperimentConfig) -> None:
    state = ExperimentState()
    devices = _build_devices(state)
    result = Orchestrator(config=minimal_config, devices=devices, state=state).run()

    assert result.status is ExperimentStatus.COMPLETED
    exp = result.experiment_dir.root
    assert (exp / "experiment.json").exists()
    assert (exp / "pump.csv").exists()
    assert (exp / "oscilloscope.csv").exists()
    assert not (exp / "scale.csv").exists()  # scale disabled

    steps = sorted((exp / "steps").iterdir())
    assert len(steps) == 2
    for step in steps:
        meta = json.loads((step / "step.json").read_text())
        assert meta["status"] in {StepStatus.COMPLETED.value, StepStatus.COMPLETED_NO_IMAGING.value}
        assert (step / "images").exists()


def test_ctrl_c_aborts_cleanly(minimal_config: ExperimentConfig) -> None:
    state = ExperimentState()
    devices = _build_devices(state)
    result = _run(minimal_config, devices, stop_after_s=0.2)
    assert result.status is ExperimentStatus.ABORTED


def test_camera_failure_marks_experiment_failed(minimal_config: ExperimentConfig) -> None:
    state = ExperimentState()
    cam = FakeCamera(fail_after_triggers=1)
    devices = _build_devices(state, camera=cam)
    result = Orchestrator(config=minimal_config, devices=devices, state=state).run()

    assert result.status is ExperimentStatus.FAILED
    steps = sorted((result.experiment_dir.root / "steps").iterdir())
    failed = [
        s
        for s in steps
        if json.loads((s / "step.json").read_text())["status"] == StepStatus.CAMERA_FAILED.value
    ]
    assert len(failed) >= 1


def test_scale_enabled_writes_scale_csv(minimal_config: ExperimentConfig) -> None:
    cfg = minimal_config.model_copy(
        update={
            "devices": minimal_config.devices.model_copy(
                update={
                    "scale": minimal_config.devices.scale.model_copy(
                        update={"enabled": True, "port": "COM5"}
                    )
                }
            )
        }
    )
    state = ExperimentState()
    devices = _build_devices(state)
    result = Orchestrator(config=cfg, devices=devices, state=state).run()
    assert (result.experiment_dir.root / "scale.csv").exists()
