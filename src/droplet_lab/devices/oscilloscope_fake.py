"""In-memory oscilloscope simulator. Generates measurements correlated with the
current ``ExperimentState`` so end-to-end tests see meaningful CSV rows.
"""

from __future__ import annotations

import random
from types import TracebackType

from droplet_lab.devices.base import ScopeMeasurement
from droplet_lab.state import ExperimentState


class FakeOscilloscope:
    def __init__(
        self,
        *,
        state: ExperimentState,
        seed: int = 0,
        noise_amplitude: float = 0.02,
    ) -> None:
        self._state = state
        self._rng = random.Random(seed)
        self._noise = noise_amplitude
        self._open = False

    def __enter__(self) -> FakeOscilloscope:
        self._open = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._open = False

    def identify(self) -> str:
        return "FakeOscilloscope (droplet_lab simulator)"

    def measure(self) -> ScopeMeasurement:
        rpm = self._state.set_speed_rpm or 0
        frequency_hz = self._state.set_frequency_hz or 200.0
        amplitude_vpp = self._state.set_amplitude_vpp
        noise = self._rng.uniform(-self._noise, self._noise)
        if amplitude_vpp is None or amplitude_vpp <= 0:
            vpp = max(0.0, 0.001 * rpm + 0.05 + noise)
        else:
            vpp = max(0.0, 0.2 * amplitude_vpp + 0.0005 * frequency_hz + noise)
        return ScopeMeasurement(
            frequency_hz=frequency_hz + noise * 5.0,
            vpp_v=round(vpp, 6),
            ch2_vrms_dc_v=round(0.5 + noise * 0.2, 6),
            ch3_vrms_dc_v=round(0.5 + noise * 0.2, 6),
        )
