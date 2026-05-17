"""Sartorius balance driver (RS-232, 7E1 framing).

The balance prints a line whenever ``PRINT`` is pressed or autoprint is enabled.
Lines look like ``"+   12.345 g\\r\\n"``. Sign and unit are stripped; we return
grams.
"""

from __future__ import annotations

import re
from types import TracebackType

import serial
from loguru import logger

_LINE_RE = re.compile(r"^\s*(?P<sign>[+-])?\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>[a-zA-Z]*)?")


class SartoriusScale:
    def __init__(
        self,
        *,
        port: str,
        baudrate: int = 1200,
        timeout_s: float = 1.0,
    ) -> None:
        self._port = port
        self._baudrate = baudrate
        self._timeout_s = timeout_s
        self._ser: serial.Serial | None = None
        self._log = logger.bind(component="scale")

    def __enter__(self) -> SartoriusScale:
        self._ser = serial.Serial(
            port=self._port,
            baudrate=self._baudrate,
            bytesize=serial.SEVENBITS,
            parity=serial.PARITY_EVEN,
            stopbits=serial.STOPBITS_ONE,
            timeout=self._timeout_s,
            xonxoff=True,
        )
        self._log.info("opened scale on {}", self._port)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._ser is not None and self._ser.is_open:
            self._ser.close()
        self._ser = None

    def read_weight_g(self) -> float | None:
        if self._ser is None:
            raise RuntimeError("Scale is not open")
        line = self._ser.readline().decode("ascii", errors="replace")
        match = _LINE_RE.match(line)
        if match is None:
            return None
        try:
            value = float(match.group("value"))
        except ValueError:
            return None
        if match.group("sign") == "-":
            value = -value
        return value
