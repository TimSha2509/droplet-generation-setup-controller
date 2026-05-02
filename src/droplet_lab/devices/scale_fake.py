"""In-memory scale simulator (monotonically increasing mass)."""

from __future__ import annotations

import random
from types import TracebackType


class FakeScale:
    def __init__(
        self,
        *,
        seed: int = 0,
        rate_g_per_s: float = 0.5,
        noise_g: float = 0.005,
    ) -> None:
        self._rng = random.Random(seed)
        self._rate = rate_g_per_s
        self._noise = noise_g
        self._weight = 0.0
        self._open = False

    def __enter__(self) -> "FakeScale":
        self._open = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._open = False

    def read_weight_g(self) -> float | None:
        return round(self._weight + self._rng.uniform(-self._noise, self._noise), 4)

    def advance(self, seconds: float) -> None:
        self._weight += self._rate * seconds
