"""In-memory pump simulator for tests and dry runs.

Models RPM as first-order approach to target with constant acceleration limit,
and temperature as a slow log-normal drift correlated with running speed.
Deterministic given a seed.
"""

from __future__ import annotations

import math
import random
from types import TracebackType


class FakePump:
    """Drop-in replacement for the real pump. No serial, no hardware."""

    def __init__(
        self,
        *,
        seed: int = 0,
        acceleration_rpm_per_s: float = 200.0,
        ambient_temp_c: float = 22.0,
    ) -> None:
        self._rng = random.Random(seed)
        self._accel = acceleration_rpm_per_s
        self._target_rpm: int = 0
        self._actual_rpm: float = 0.0
        self._temp_c: float = ambient_temp_c
        self._ambient = ambient_temp_c
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    def __enter__(self) -> "FakePump":
        self._open = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._open = False

    def set_speed(self, rpm: int) -> None:
        if rpm < 0:
            raise ValueError(f"rpm must be >= 0, got {rpm}")
        self._target_rpm = rpm

    def stop(self) -> None:
        self._target_rpm = 0

    def get_actual_speed_rpm(self) -> int | None:
        return int(round(self._actual_rpm))

    def get_target_speed_rpm(self) -> int | None:
        return self._target_rpm

    def get_temperature_c(self) -> float | None:
        return round(self._temp_c, 2)

    def advance(self, seconds: float) -> None:
        """Advance the simulator clock (test helper, not on Protocol)."""
        delta = self._target_rpm - self._actual_rpm
        max_change = self._accel * seconds
        if abs(delta) <= max_change:
            self._actual_rpm = float(self._target_rpm)
        else:
            self._actual_rpm += math.copysign(max_change, delta)

        # Heat up when running, cool toward ambient otherwise.
        load = self._actual_rpm / 1000.0
        equilibrium = self._ambient + 25.0 * load
        self._temp_c += (equilibrium - self._temp_c) * min(1.0, seconds * 0.05)
        self._temp_c += self._rng.uniform(-0.05, 0.05) * seconds
