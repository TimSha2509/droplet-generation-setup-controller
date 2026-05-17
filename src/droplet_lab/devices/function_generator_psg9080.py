"""PSG9080 function generator driver (serial, ASCII command protocol).

Commands (channel 1 / channel 2):
    :w11=0.        / :w12=0.            — set sine wave
    :w13=<n>,0.    / :w14=<n>,0.        — frequency, n = Hz × 1000
    :w15=<n>.      / :w16=<n>.          — amplitude, n = Vpp × 1000
    :w10=<a>,<b>.                       — output enable (a=Ch1, b=Ch2 in {0,1})
"""

from __future__ import annotations

import time
from types import TracebackType
from typing import Final

import serial
from loguru import logger

from droplet_lab.config import MAX_AMPLITUDE_VPP

__all__ = ["PSG9080Generator", "MAX_AMPLITUDE_VPP"]

_RESPONSE_READ_DELAY_S: Final[float] = 0.05
_OPEN_SETTLE_S: Final[float] = 0.2


class PSG9080Generator:
    def __init__(
        self,
        *,
        port: str,
        channel: int = 1,
        baudrate: int = 115200,
        timeout_s: float = 1.0,
    ) -> None:
        if channel not in (1, 2):
            raise ValueError(f"channel must be 1 or 2, got {channel}")
        self._port = port
        self._channel = channel
        self._baudrate = baudrate
        self._timeout_s = timeout_s
        self._ser: serial.Serial | None = None
        self._log = logger.bind(component="fg")

    def __enter__(self) -> PSG9080Generator:
        self._ser = serial.Serial(
            port=self._port,
            baudrate=self._baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self._timeout_s,
        )
        time.sleep(_OPEN_SETTLE_S)
        self._log.info("opened PSG9080 on {} (channel {})", self._port, self._channel)
        self.set_sine()
        self.enable_output(False)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._ser is not None and self._ser.is_open:
            try:
                self.enable_output(False)
            finally:
                self._ser.close()
        self._ser = None

    def set_sine(self) -> None:
        cmd = ":w11=0." if self._channel == 1 else ":w12=0."
        self._send(cmd)

    def set_frequency_hz(self, hz: float) -> None:
        scaled = int(round(hz * 1000))
        cmd = (
            f":w13={scaled},0."
            if self._channel == 1
            else f":w14={scaled},0."
        )
        self._send(cmd)

    def set_amplitude_vpp(self, vpp: float) -> None:
        if vpp > MAX_AMPLITUDE_VPP:
            raise ValueError(
                f"amplitude {vpp} Vpp exceeds hardware limit {MAX_AMPLITUDE_VPP} Vpp"
            )
        scaled = int(round(vpp * 1000))
        cmd = (
            f":w15={scaled}."
            if self._channel == 1
            else f":w16={scaled}."
        )
        self._send(cmd)

    def enable_output(self, on: bool) -> None:
        if self._channel == 1:
            cmd = f":w10={1 if on else 0},0."
        else:
            cmd = f":w10=0,{1 if on else 0}."
        self._send(cmd)

    def _send(self, command: str) -> None:
        if self._ser is None:
            raise RuntimeError("PSG9080 is not open")
        full = (command + "\r\n").encode("ascii")
        self._ser.write(full)
        time.sleep(_RESPONSE_READ_DELAY_S)
        response = self._ser.read_all().decode("ascii", errors="ignore").strip()
        if response:
            self._log.debug("fg sent={!r} resp={!r}", command, response)
        else:
            self._log.debug("fg sent={!r}", command)
