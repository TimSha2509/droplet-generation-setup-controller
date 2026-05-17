"""Pydantic v2 models for experiment configuration.

A complete experiment is one YAML file under ``experiments/``. ``load_experiment``
parses, validates, and returns an ``ExperimentConfig``. Any structural problem in
the YAML (typo, wrong type, missing field, value out of range) raises
``ValidationError`` with a precise location.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Final, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    PositiveFloat,
    PositiveInt,
    field_validator,
    model_validator,
)

MAX_AMPLITUDE_VPP: Final[float] = 9.5


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VibrometerConfig(_StrictModel):
    factor_um_per_v: PositiveFloat


class SweepConfig(_StrictModel):
    speeds_rpm: Annotated[list[PositiveInt], Field(min_length=1)]
    frequencies_hz: Annotated[list[PositiveFloat], Field(min_length=1)]
    amplitudes_vpp: Annotated[list[PositiveFloat], Field(min_length=1)]
    hold_s: PositiveFloat

    @field_validator("amplitudes_vpp")
    @classmethod
    def _amplitudes_within_hardware_limit(cls, value: list[float]) -> list[float]:
        for amp in value:
            if amp > MAX_AMPLITUDE_VPP:
                raise ValueError(
                    f"amplitude {amp} Vpp exceeds hardware limit {MAX_AMPLITUDE_VPP} Vpp"
                )
        return value


class TimingConfig(_StrictModel):
    stabilization_rpm_change_s: NonNegativeFloat
    stabilization_freq_change_s: NonNegativeFloat
    stabilization_amp_change_s: NonNegativeFloat
    image_interval_s: PositiveFloat
    camera_latency_tolerance_s: NonNegativeFloat = 0.0


class LimitsConfig(_StrictModel):
    max_speed_rpm: PositiveInt = 1000


class PumpConfig(_StrictModel):
    port: str
    baudrate: PositiveInt = 9600


class OscilloscopeConfig(_StrictModel):
    visa_resource: str
    timeout_ms: PositiveInt = 5000


class CameraConfig(_StrictModel):
    digicam_url: str = "http://localhost:5513"
    request_timeout_s: PositiveFloat = 10.0


class FunctionGeneratorConfig(_StrictModel):
    port: str
    channel: Literal[1, 2] = 1
    baudrate: PositiveInt = 115200


class ScaleConfig(_StrictModel):
    enabled: bool = False
    port: str | None = None
    baudrate: PositiveInt = 1200
    interval_s: PositiveFloat = 5.0


class DevicesConfig(_StrictModel):
    pump: PumpConfig
    oscilloscope: OscilloscopeConfig
    camera: CameraConfig
    function_generator: FunctionGeneratorConfig
    scale: ScaleConfig = Field(default_factory=ScaleConfig)


class OutputConfig(_StrictModel):
    base_dir: Path

    @field_validator("base_dir", mode="after")
    @classmethod
    def _resolve(cls, value: Path) -> Path:
        return value.expanduser().resolve()


class ExperimentConfig(_StrictModel):
    experiment_id: str = Field(min_length=1)
    nozzle_id: str = Field(min_length=1)
    vibrometer: VibrometerConfig
    sweep: SweepConfig
    timing: TimingConfig
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    devices: DevicesConfig
    output: OutputConfig

    @model_validator(mode="after")
    def _speeds_within_limits(self) -> ExperimentConfig:
        max_rpm = self.limits.max_speed_rpm
        for i, rpm in enumerate(self.sweep.speeds_rpm):
            if rpm > max_rpm:
                raise ValueError(
                    f"sweep.speeds_rpm[{i}]={rpm} exceeds limits.max_speed_rpm={max_rpm}"
                )
        return self

    @model_validator(mode="after")
    def _hold_s_covers_rpm_stabilization(self) -> ExperimentConfig:
        if self.sweep.hold_s < self.timing.stabilization_rpm_change_s:
            raise ValueError(
                f"sweep.hold_s={self.sweep.hold_s} must be >= "
                f"timing.stabilization_rpm_change_s={self.timing.stabilization_rpm_change_s}"
            )
        return self


def load_experiment(path: Path | str) -> ExperimentConfig:
    """Load and validate an experiment YAML file."""
    raw = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping at the YAML root")
    return ExperimentConfig.model_validate(data)
