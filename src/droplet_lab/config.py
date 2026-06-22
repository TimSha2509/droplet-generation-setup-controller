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
    amplitudes_vpp: Annotated[list[PositiveFloat], Field(min_length=1)] | None = None
    displacements_um: Annotated[list[PositiveFloat], Field(min_length=1)] | None = None
    hold_s: PositiveFloat
    random: bool = False

    @field_validator("amplitudes_vpp")
    @classmethod
    def _amplitudes_within_hardware_limit(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return value
        for amp in value:
            if amp > MAX_AMPLITUDE_VPP:
                raise ValueError(
                    f"amplitude {amp} Vpp exceeds hardware limit {MAX_AMPLITUDE_VPP} Vpp"
                )
        return value

    @model_validator(mode="after")
    def _exactly_one_actuation_axis(self) -> SweepConfig:
        has_amplitudes = self.amplitudes_vpp is not None
        has_displacements = self.displacements_um is not None
        if has_amplitudes == has_displacements:
            raise ValueError(
                "exactly one of sweep.amplitudes_vpp or sweep.displacements_um is required"
            )
        return self


class TimingConfig(_StrictModel):
    stabilization_rpm_change_s: NonNegativeFloat
    stabilization_freq_change_s: NonNegativeFloat
    stabilization_amp_change_s: NonNegativeFloat
    image_interval_s: PositiveFloat
    camera_latency_tolerance_s: NonNegativeFloat = 0.0
    wait_time_camera: NonNegativeFloat = 0.0


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
    trigger_backend: Literal["digicam", "arduino"] = "digicam"
    shutter_port: str | None = None
    shutter_baudrate: PositiveInt = 9600
    shutter_pulse_ms: PositiveInt = 300
    shutter_read_timeout_s: PositiveFloat = 2.0

    @model_validator(mode="after")
    def _arduino_requires_port(self) -> CameraConfig:
        if self.trigger_backend == "arduino" and not self.shutter_port:
            raise ValueError("devices.camera.shutter_port is required for Arduino triggering")
        return self


class FunctionGeneratorConfig(_StrictModel):
    port: str
    channel: Literal[1, 2] = 1
    baudrate: PositiveInt = 115200


class ScaleConfig(_StrictModel):
    enabled: bool = False
    port: str | None = None
    baudrate: PositiveInt = 1200
    interval_s: PositiveFloat = 5.0


class DisplacementConfig(_StrictModel):
    model_path: Path | None = None
    max_voltage_table_path: Path | None = None
    amplifier_gain: PositiveFloat = 2.0
    calibration_start_hz: PositiveFloat = 10.0
    calibration_stop_hz: PositiveFloat = 120.0
    calibration_step_hz: PositiveFloat = 10.0
    voltage_steps: Annotated[int, Field(ge=2)] = 5
    measurement_s: PositiveFloat = 10.0
    scope_interval_s: PositiveFloat = 0.5
    validation_enabled: bool = False
    validation_threshold_percent: PositiveFloat = 10.0

    @field_validator("model_path", "max_voltage_table_path", mode="after")
    @classmethod
    def _resolve_optional_path(cls, value: Path | None) -> Path | None:
        if value is None:
            return value
        return value.expanduser().resolve()

    @model_validator(mode="after")
    def _calibration_range_valid(self) -> DisplacementConfig:
        if self.calibration_stop_hz < self.calibration_start_hz:
            raise ValueError("displacement.calibration_stop_hz must be >= calibration_start_hz")
        return self


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
    displacement: DisplacementConfig = Field(default_factory=DisplacementConfig)
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
    def _displacement_mode_requires_model_path(self) -> ExperimentConfig:
        if self.sweep.displacements_um is not None and self.displacement.model_path is None:
            raise ValueError(
                "displacement.model_path is required when using sweep.displacements_um"
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
