"""DigiCamControl folder routing with Arduino remote-shutter triggering."""

from __future__ import annotations

import time
from pathlib import Path
from types import TracebackType
from typing import cast

import requests
import serial
from loguru import logger


class DigiCamArduinoCamera:
    def __init__(
        self,
        *,
        digicam_url: str = "http://localhost:5513",
        request_timeout_s: float = 10.0,
        shutter_port: str,
        shutter_baudrate: int = 9600,
        shutter_pulse_ms: int = 300,
        shutter_read_timeout_s: float = 2.0,
    ) -> None:
        self._digicam_url = digicam_url
        self._request_timeout_s = request_timeout_s
        self._shutter_port = shutter_port
        self._shutter_baudrate = shutter_baudrate
        self._shutter_pulse_ms = shutter_pulse_ms
        self._shutter_read_timeout_s = shutter_read_timeout_s
        self._serial: serial.Serial | None = None
        self._log = logger.bind(component="camera")

    def __enter__(self) -> DigiCamArduinoCamera:
        self._serial = serial.Serial(
            self._shutter_port,
            baudrate=self._shutter_baudrate,
            timeout=self._shutter_read_timeout_s,
            write_timeout=self._shutter_read_timeout_s,
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._serial is None:
            return
        try:
            self._write_line("release")
        except Exception as e:
            self._log.warning("failed to release Arduino shutter during camera close: {}", e)
        finally:
            self._serial.close()
            self._serial = None

    def _get(self, params: dict[str, str]) -> None:
        response = requests.get(self._digicam_url, params=params, timeout=self._request_timeout_s)
        response.raise_for_status()

    def _write_line(self, command: str) -> None:
        if self._serial is None:
            raise RuntimeError("camera shutter serial port is not open")
        self._serial.write(f"{command}\n".encode("ascii"))
        self._serial.flush()

    def _read_response(self) -> str:
        if self._serial is None:
            raise RuntimeError("camera shutter serial port is not open")
        deadline = time.monotonic() + self._shutter_read_timeout_s
        ignored: list[str] = []
        while True:
            remaining_s = deadline - time.monotonic()
            if remaining_s <= 0:
                detail = f"; ignored: {ignored}" if ignored else ""
                raise TimeoutError(f"timed out waiting for Arduino shutter response{detail}")
            self._serial.timeout = remaining_s
            raw = cast(bytes, self._serial.readline())
            if not raw:
                detail = f"; ignored: {ignored}" if ignored else ""
                raise TimeoutError(f"timed out waiting for Arduino shutter response{detail}")
            response = raw.decode("ascii", errors="replace").strip()
            if response.startswith(("OK", "ERR")):
                return response
            ignored.append(response)
            self._log.debug("ignoring Arduino shutter serial line: {}", response)

    def set_output_folder(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        self._get({"slc": "set", "param1": "session.folder", "param2": str(folder)})
        self._log.info("camera folder set to {}", folder)

    def trigger_capture(self) -> None:
        self._write_line(f"shoot {self._shutter_pulse_ms}")
        response = self._read_response()
        if response.startswith("ERR"):
            raise RuntimeError(f"Arduino shutter error: {response}")
        if not response.startswith("OK shoot"):
            raise RuntimeError(f"unexpected Arduino shutter response: {response}")
