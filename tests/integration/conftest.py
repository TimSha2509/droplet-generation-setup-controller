from pathlib import Path

import pytest

from droplet_lab.config import (
    CameraConfig,
    DevicesConfig,
    ExperimentConfig,
    FunctionGeneratorConfig,
    LimitsConfig,
    OscilloscopeConfig,
    OutputConfig,
    PumpConfig,
    ScaleConfig,
    SweepConfig,
    TimingConfig,
    VibrometerConfig,
)


@pytest.fixture
def minimal_config(tmp_path: Path) -> ExperimentConfig:
    """Tiny sweep (1 rpm x 1 freq x 1 amp) suitable for fast integration tests."""
    return ExperimentConfig(
        experiment_id="INT_TEST",
        nozzle_id="1mm_A",
        vibrometer=VibrometerConfig(factor_um_per_v=5280),
        sweep=SweepConfig(
            speeds_rpm=[200],
            frequencies_hz=[20.0],
            amplitudes_vpp=[3.0],
            hold_s=0.4,
        ),
        timing=TimingConfig(
            stabilization_rpm_change_s=0.1,
            stabilization_freq_change_s=0.05,
            stabilization_amp_change_s=0.02,
            image_interval_s=0.1,
            camera_latency_tolerance_s=0.05,
        ),
        limits=LimitsConfig(max_speed_rpm=1000),
        devices=DevicesConfig(
            pump=PumpConfig(port="COM3"),
            oscilloscope=OscilloscopeConfig(visa_resource="USB"),
            camera=CameraConfig(),
            function_generator=FunctionGeneratorConfig(port="COM4"),
            scale=ScaleConfig(enabled=False),
        ),
        output=OutputConfig(base_dir=tmp_path),
    )
