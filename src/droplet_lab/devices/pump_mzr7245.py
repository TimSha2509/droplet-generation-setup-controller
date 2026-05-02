"""Ismatec MZR-7245 gear pump driver over RS-232.

Command set used:
    V<rpm>  -- set target speed
    GN      -- query actual speed (rpm)
    GV      -- query target speed (rpm)
    TEM     -- query temperature (degrees C)
"""

from __future__ import annotations

import time
from types import TracebackType

import serial
from loguru import logger


def _safe_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return None


class MZR7245Pump:
    def __init__(
        self,
        *,
        port: str,
        baudrate: int = 9600,
        timeout_s: float = 1.0,
        post_open_delay_s: float = 2.0,
    ) -> None:
        self._port = port
        self._baudrate = baudrate
        self._timeout_s = timeout_s
        self._post_open_delay_s = post_open_delay_s
        self._ser: serial.Serial | None = None
        self._log = logger.bind(component="pump")

    def __enter__(self) -> MZR7245Pump:
        self._ser = serial.Serial(
            port=self._port,
            baudrate=self._baudrate,
            timeout=self._timeout_s,
        )
        time.sleep(self._post_open_delay_s)
        self._log.info("opened pump on {} @ {} baud", self._port, self._baudrate)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._ser is not None and self._ser.is_open:
            try:
                self._ser.close()
            finally:
                self._log.info("closed pump")
        self._ser = None

    def _cmd(self, command: str, pause: float = 0.2) -> str | None:
        if self._ser is None:
            raise RuntimeError("Pump is not open")
        self._ser.reset_input_buffer()
        self._ser.write((command + "\r").encode("ascii"))
        self._ser.flush()
        time.sleep(pause)
        raw = self._ser.read_all() or b""
        reply = raw.decode("ascii", errors="replace").strip()
        self._log.debug("cmd {!r} -> {!r}", command, reply)
        return reply or None

    def set_speed(self, rpm: int) -> None:
        if rpm < 0:
            raise ValueError(f"rpm must be >= 0, got {rpm}")
        self._cmd(f"V{int(rpm)}")

    def stop(self) -> None:
        self._cmd("V0")

    def get_actual_speed_rpm(self) -> int | None:
        return _safe_int(self._cmd("GN"))

    def get_target_speed_rpm(self) -> int | None:
        return _safe_int(self._cmd("GV"))

    def get_temperature_c(self) -> float | None:
        raw = self._cmd("TEM")
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError:
            return None
