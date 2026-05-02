"""Pydantic v2 models for experiment configuration.

A complete experiment is one YAML file under ``experiments/``. ``load_experiment``
parses, validates, and returns an ``ExperimentConfig``. Any structural problem in
the YAML (typo, wrong type, missing field, value out of range) raises
``ValidationError`` with a precise location.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

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


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ActuationConfig(_StrictModel):
    frequency_hz: PositiveFloat
    voltage_v: PositiveFloat
    vibrometer_factor_um_per_v: PositiveFloat


class RampStep(_StrictModel):
    speed_rpm: PositiveInt
    hold_s: PositiveFloat


class TimingConfig(_StrictModel):
    stabilization_s: NonNegativeFloat
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


class ScaleConfig(_StrictModel):
    enabled: bool = False
    port: str | None = None
    baudrate: PositiveInt = 9600


class DevicesConfig(_StrictModel):
    pump: PumpConfig
    oscilloscope: OscilloscopeConfig
    camera: CameraConfig
    scale: ScaleConfig = Field(default_factory=ScaleConfig)


class OutputConfig(_StrictModel):
    base_dir: Path

    @field_validator("base_dir", mode="after")
    @classmethod
    def _resolve(cls, value: Path) -> Path:
        return value.expanduser().resolve()


RampProfile = Annotated[list[RampStep], Field(min_length=1)]


class ExperimentConfig(_StrictModel):
    experiment_id: str = Field(min_length=1)
    nozzle_id: str = Field(min_length=1)
    actuation: ActuationConfig
    ramp: RampProfile
    timing: TimingConfig
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    devices: DevicesConfig
    output: OutputConfig

    @model_validator(mode="after")
    def _ramp_within_limits(self) -> ExperimentConfig:
        max_rpm = self.limits.max_speed_rpm
        for i, step in enumerate(self.ramp):
            if step.speed_rpm > max_rpm:
                raise ValueError(
                    f"ramp[{i}].speed_rpm={step.speed_rpm} exceeds "
                    f"limits.max_speed_rpm={max_rpm}"
                )
        return self


def load_experiment(path: Path | str) -> ExperimentConfig:
    """Load and validate an experiment YAML file."""
    raw = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping at the YAML root")
    return ExperimentConfig.model_validate(data)
