from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from droplet_lab.config import (
    MAX_AMPLITUDE_VPP,
    CameraConfig,
    DevicesConfig,
    ExperimentConfig,
    FunctionGeneratorConfig,
    OscilloscopeConfig,
    OutputConfig,
    PumpConfig,
    ScaleConfig,
    SweepConfig,
    VibrometerConfig,
    load_experiment,
)


def _minimal_dict(tmp_path: Path) -> dict[str, object]:
    return {
        "experiment_id": "TEST_01",
        "nozzle_id": "1mm_A",
        "vibrometer": {"factor_um_per_v": 5280},
        "sweep": {
            "speeds_rpm": [200, 250],
            "frequencies_hz": [20.0, 25.0],
            "amplitudes_vpp": [3.0, 5.0],
            "hold_s": 1.0,
        },
        "timing": {
            "stabilization_rpm_change_s": 0.5,
            "stabilization_freq_change_s": 0.2,
            "stabilization_amp_change_s": 0.1,
            "image_interval_s": 0.5,
            "camera_latency_tolerance_s": 0.5,
        },
        "limits": {"max_speed_rpm": 1000},
        "devices": {
            "pump": {"port": "COM3", "baudrate": 9600},
            "oscilloscope": {"visa_resource": "USB0::INSTR"},
            "camera": {"digicam_url": "http://localhost:5513"},
            "function_generator": {"port": "COM4", "channel": 1, "baudrate": 115200},
            "scale": {"enabled": False},
        },
        "output": {"base_dir": str(tmp_path)},
    }


def test_minimal_config_validates(tmp_path: Path) -> None:
    cfg = ExperimentConfig.model_validate(_minimal_dict(tmp_path))
    assert cfg.experiment_id == "TEST_01"
    assert cfg.vibrometer.factor_um_per_v == 5280
    assert cfg.sweep.speeds_rpm == [200, 250]
    assert cfg.devices.function_generator.channel == 1
    assert cfg.devices.scale.enabled is False


def test_amplitude_above_hardware_limit_rejected(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    data["sweep"]["amplitudes_vpp"] = [3.0, 10.0]
    with pytest.raises(ValidationError) as exc:
        ExperimentConfig.model_validate(data)
    assert "hardware limit" in str(exc.value)


def test_max_amplitude_constant() -> None:
    assert MAX_AMPLITUDE_VPP == 9.5


def test_empty_speeds_rejected(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    data["sweep"]["speeds_rpm"] = []
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(data)


def test_empty_frequencies_rejected(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    data["sweep"]["frequencies_hz"] = []
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(data)


def test_empty_amplitudes_rejected(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    data["sweep"]["amplitudes_vpp"] = []
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(data)


def test_speed_above_limit_rejected(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    data["sweep"]["speeds_rpm"] = [1500]
    with pytest.raises(ValidationError) as exc:
        ExperimentConfig.model_validate(data)
    assert "max_speed_rpm" in str(exc.value)


def test_hold_s_must_cover_rpm_stabilization(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    data["sweep"]["hold_s"] = 0.2
    data["timing"]["stabilization_rpm_change_s"] = 0.5
    with pytest.raises(ValidationError) as exc:
        ExperimentConfig.model_validate(data)
    assert "stabilization_rpm_change_s" in str(exc.value)


def test_function_generator_channel_must_be_1_or_2(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    data["devices"]["function_generator"]["channel"] = 3
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(data)


def test_unknown_field_rejected(tmp_path: Path) -> None:
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


def test_pump_config_defaults() -> None:
    cfg = PumpConfig(port="COM3")
    assert cfg.baudrate == 9600


def test_function_generator_defaults() -> None:
    cfg = FunctionGeneratorConfig(port="COM4")
    assert cfg.channel == 1
    assert cfg.baudrate == 115200


def test_scale_defaults() -> None:
    cfg = ScaleConfig()
    assert cfg.enabled is False
    assert cfg.port is None
    assert cfg.baudrate == 1200
    assert cfg.interval_s == 5.0


def test_devices_config_partial() -> None:
    devices = DevicesConfig(
        pump=PumpConfig(port="COM3"),
        oscilloscope=OscilloscopeConfig(visa_resource="USB0::INSTR"),
        camera=CameraConfig(digicam_url="http://localhost:5513"),
        function_generator=FunctionGeneratorConfig(port="COM4"),
        scale=ScaleConfig(),
    )
    assert devices.scale.enabled is False
    assert devices.function_generator.channel == 1


def test_example_yaml_validates() -> None:
    """The shipped example YAML must always validate."""
    cfg = load_experiment(Path("experiments/example_hpmc.yaml"))
    assert cfg.experiment_id


def test_output_config_resolves_path(tmp_path: Path) -> None:
    cfg = OutputConfig(base_dir=tmp_path)
    assert cfg.base_dir.is_absolute()


def test_vibrometer_factor_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        VibrometerConfig(factor_um_per_v=0)


def test_sweep_config_standalone() -> None:
    s = SweepConfig(
        speeds_rpm=[200], frequencies_hz=[20.0], amplitudes_vpp=[3.0], hold_s=1.0
    )
    assert s.speeds_rpm == [200]
