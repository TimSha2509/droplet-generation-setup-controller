from pathlib import Path

import pytest

from droplet_lab.config import (
    ActuationConfig,
    CameraConfig,
    DevicesConfig,
    ExperimentConfig,
    LimitsConfig,
    OscilloscopeConfig,
    OutputConfig,
    PumpConfig,
    RampStep,
    ScaleConfig,
    TimingConfig,
)


@pytest.fixture
def minimal_config(tmp_path: Path) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="INT_TEST",
        nozzle_id="1mm_A",
        actuation=ActuationConfig(
            frequency_hz=200,
            voltage_v=5,
            vibrometer_factor_um_per_v=5280,
        ),
        ramp=[
            RampStep(speed_rpm=200, hold_s=0.4),
            RampStep(speed_rpm=300, hold_s=0.4),
        ],
        timing=TimingConfig(
            stabilization_s=0.1,
            image_interval_s=0.1,
            camera_latency_tolerance_s=0.05,
        ),
        limits=LimitsConfig(max_speed_rpm=1000),
        devices=DevicesConfig(
            pump=PumpConfig(port="COM3"),
            oscilloscope=OscilloscopeConfig(visa_resource="USB"),
            camera=CameraConfig(),
            scale=ScaleConfig(enabled=False),
        ),
        output=OutputConfig(base_dir=tmp_path),
    )
