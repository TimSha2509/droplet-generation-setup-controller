"""In-memory function generator simulator."""

from __future__ import annotations

from types import TracebackType
from typing import Any

from loguru import logger

from droplet_lab.config import MAX_AMPLITUDE_VPP


class FakeFunctionGenerator:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.is_sine: bool = False
        self.frequency_hz: float | None = None
        self.amplitude_vpp: float | None = None
        self.output_on: bool = False
        self._open = False
        self._log = logger.bind(component="fg")

    def __enter__(self) -> FakeFunctionGenerator:
        self._open = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.output_on = False
        self._open = False

    def set_sine(self) -> None:
        self.calls.append(("set_sine",))
        self.is_sine = True
        self._log.debug("fake fg: set_sine")

    def set_frequency_hz(self, hz: float) -> None:
        self.calls.append(("set_frequency_hz", float(hz)))
        self.frequency_hz = float(hz)
        self._log.debug("fake fg: frequency={} Hz", hz)

    def set_amplitude_vpp(self, vpp: float) -> None:
        if vpp > MAX_AMPLITUDE_VPP:
            raise ValueError(
                f"amplitude {vpp} Vpp exceeds hardware limit {MAX_AMPLITUDE_VPP} Vpp"
            )
        self.calls.append(("set_amplitude_vpp", float(vpp)))
        self.amplitude_vpp = float(vpp)
        self._log.debug("fake fg: amplitude={} Vpp", vpp)

    def enable_output(self, on: bool) -> None:
        self.calls.append(("enable_output", bool(on)))
        self.output_on = bool(on)
        self._log.debug("fake fg: output={}", on)
