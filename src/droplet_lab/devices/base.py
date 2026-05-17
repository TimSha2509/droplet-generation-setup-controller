"""Protocols and value objects for hardware devices.

Every device class has a typed ``Protocol`` that doubles as a context manager.
Real implementations (``MZR7245Pump`` etc.) and fakes (``FakePump`` etc.) both
satisfy the protocol structurally — no inheritance needed.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ScopeMeasurement:
    """One sample from the oscilloscope. ``None`` means the channel/measurement failed."""

    frequency_hz: float | None
    vpp_v: float | None
    ch2_vrms_dc_v: float | None
    ch3_vrms_dc_v: float | None


class Pump(Protocol, AbstractContextManager["Pump"]):
    def set_speed(self, rpm: int) -> None: ...
    def stop(self) -> None: ...
    def get_actual_speed_rpm(self) -> int | None: ...
    def get_target_speed_rpm(self) -> int | None: ...
    def get_temperature_c(self) -> float | None: ...


class Oscilloscope(Protocol, AbstractContextManager["Oscilloscope"]):
    def identify(self) -> str: ...
    def measure(self) -> ScopeMeasurement: ...


class Camera(Protocol, AbstractContextManager["Camera"]):
    def set_output_folder(self, folder: Path) -> None: ...
    def trigger_capture(self) -> None: ...


class Scale(Protocol, AbstractContextManager["Scale"]):
    def read_weight_g(self) -> float | None: ...


class FunctionGenerator(Protocol, AbstractContextManager["FunctionGenerator"]):
    def set_sine(self) -> None: ...
    def set_frequency_hz(self, hz: float) -> None: ...
    def set_amplitude_vpp(self, vpp: float) -> None: ...
    def enable_output(self, on: bool) -> None: ...
