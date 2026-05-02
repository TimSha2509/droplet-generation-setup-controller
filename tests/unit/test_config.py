from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from droplet_lab.config import (
    ActuationConfig,
    CameraConfig,
    DevicesConfig,
    ExperimentConfig,
    OscilloscopeConfig,
    OutputConfig,
    PumpConfig,
    RampStep,
    ScaleConfig,
    load_experiment,
)


def _minimal_dict(tmp_path: Path) -> dict[str, object]:
    return {
        "experiment_id": "TEST_01",
        "nozzle_id": "1mm_A",
        "actuation": {
            "frequency_hz": 200,
            "voltage_v": 5,
            "vibrometer_factor_um_per_v": 5280,
        },
        "ramp": [
            {"speed_rpm": 200, "hold_s": 1.0},
            {"speed_rpm": 250, "hold_s": 1.0},
        ],
        "timing": {
            "stabilization_s": 0.1,
            "image_interval_s": 0.5,
            "camera_latency_tolerance_s": 0.5,
        },
        "limits": {"max_speed_rpm": 1000},
        "devices": {
            "pump": {"port": "COM3", "baudrate": 9600},
            "oscilloscope": {"visa_resource": "USB0::INSTR"},
            "camera": {"digicam_url": "http://localhost:5513"},
            "scale": {"enabled": False},
        },
        "output": {"base_dir": str(tmp_path)},
    }


def test_minimal_config_validates(tmp_path: Path) -> None:
    cfg = ExperimentConfig.model_validate(_minimal_dict(tmp_path))
    assert cfg.experiment_id == "TEST_01"
    assert cfg.actuation.frequency_hz == 200
    assert len(cfg.ramp) == 2
    assert cfg.devices.scale.enabled is False
    assert cfg.output.base_dir == tmp_path.resolve()


def test_ramp_step_rejects_zero_speed() -> None:
    with pytest.raises(ValidationError):
        RampStep(speed_rpm=0, hold_s=1.0)


def test_ramp_step_rejects_negative_hold() -> None:
    with pytest.raises(ValidationError):
        RampStep(speed_rpm=200, hold_s=-1.0)


def test_ramp_must_not_be_empty(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    data["ramp"] = []
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(data)


def test_ramp_speed_must_not_exceed_limit(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    data["ramp"] = [{"speed_rpm": 1500, "hold_s": 1.0}]  # limit is 1000
    with pytest.raises(ValidationError) as exc:
        ExperimentConfig.model_validate(data)
    assert "max_speed_rpm" in str(exc.value)


def test_unknown_field_is_rejected(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    data["unknown_field"] = "oops"
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(data)


def test_load_experiment_from_yaml(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    yaml_path = tmp_path / "exp.yaml"
    yaml_path.write_text(yaml.safe_dump(data))

    cfg = load_experiment(yaml_path)
    assert cfg.experiment_id == "TEST_01"


def test_actuation_rejects_zero_frequency() -> None:
    with pytest.raises(ValidationError):
        ActuationConfig(frequency_hz=0, voltage_v=5, vibrometer_factor_um_per_v=5280)


def test_pump_config_defaults() -> None:
    cfg = PumpConfig(port="COM3")
    assert cfg.baudrate == 9600


def test_scale_disabled_by_default() -> None:
    cfg = ScaleConfig()
    assert cfg.enabled is False
    assert cfg.port is None


def test_devices_config_partial(tmp_path: Path) -> None:
    devices = DevicesConfig(
        pump=PumpConfig(port="COM3"),
        oscilloscope=OscilloscopeConfig(visa_resource="USB0::INSTR"),
        camera=CameraConfig(digicam_url="http://localhost:5513"),
        scale=ScaleConfig(),
    )
    assert devices.scale.enabled is False


def test_example_yaml_validates() -> None:
    """The shipped example YAML must always validate."""
    cfg = load_experiment(Path("experiments/example_hpmc.yaml"))
    assert cfg.experiment_id


def test_output_config_resolves_path(tmp_path: Path) -> None:
    cfg = OutputConfig(base_dir=tmp_path)
    assert cfg.base_dir.is_absolute()
