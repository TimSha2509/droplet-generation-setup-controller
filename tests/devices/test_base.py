"""Smoke tests that prove the protocols + measurement dataclasses are importable
and that measurement dataclasses are immutable."""

from dataclasses import FrozenInstanceError

import pytest

from droplet_lab.devices.base import (
    Camera,
    Oscilloscope,
    Pump,
    Scale,
    ScopeMeasurement,
)


def test_protocols_are_importable() -> None:
    assert Pump is not None
    assert Oscilloscope is not None
    assert Camera is not None
    assert Scale is not None


def test_scope_measurement_is_frozen() -> None:
    m = ScopeMeasurement(
        frequency_hz=200.0,
        vpp_v=1.0,
        ch2_vrms_dc_v=0.5,
        ch3_vrms_dc_v=0.5,
    )
    with pytest.raises(FrozenInstanceError):
        m.frequency_hz = 300.0  # type: ignore[misc]
