"""Keysight DSOX oscilloscope driver via VISA / SCPI."""

from __future__ import annotations

import contextlib
import math
from types import TracebackType
from typing import cast

import pyvisa
from loguru import logger
from pyvisa.resources import MessageBasedResource

from droplet_lab.devices.base import ScopeMeasurement

_KEYSIGHT_INVALID_SENTINEL = 9.9e37  # scope returns ~9.91E+37 when no signal


def _safe_float(text: str) -> float | None:
    try:
        value = float(text.strip())
    except (ValueError, AttributeError):
        return None
    if math.isnan(value) or math.isinf(value) or abs(value) >= _KEYSIGHT_INVALID_SENTINEL:
        return None
    return value


class KeysightOscilloscope:
    def __init__(
        self,
        *,
        visa_resource: str,
        timeout_ms: int = 5000,
    ) -> None:
        self._resource = visa_resource
        self._timeout_ms = timeout_ms
        self._rm: pyvisa.ResourceManager | None = None
        self._scope: MessageBasedResource | None = None
        self._log = logger.bind(component="scope")

    def __enter__(self) -> KeysightOscilloscope:
        self._rm = pyvisa.ResourceManager()
        self._scope = cast(MessageBasedResource, self._rm.open_resource(self._resource))
        self._scope.timeout = self._timeout_ms
        self._scope.write_termination = "\n"
        self._scope.read_termination = "\n"
        self._log.info("opened scope at {}", self._resource)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._scope is not None:
            with contextlib.suppress(Exception):
                self._scope.close()
        if self._rm is not None:
            with contextlib.suppress(Exception):
                self._rm.close()
        self._scope = None
        self._rm = None
        self._log.info("closed scope")

    def _query(self, scpi: str) -> str:
        if self._scope is None:
            raise RuntimeError("Oscilloscope is not open")
        return self._scope.query(scpi)

    def identify(self) -> str:
        return self._query("*IDN?").strip()

    def measure(self) -> ScopeMeasurement:
        return ScopeMeasurement(
            frequency_hz=_safe_float(self._query(":MEASure:FREQuency? CHANnel1")),
            vpp_v=_safe_float(self._query(":MEASure:VPP? CHANnel1")),
            ch2_vrms_dc_v=_safe_float(self._query(":MEASure:VRMS? DISPlay,DC,CHANnel2")),
            ch3_vrms_dc_v=_safe_float(self._query(":MEASure:VRMS? DISPlay,DC,CHANnel3")),
        )
