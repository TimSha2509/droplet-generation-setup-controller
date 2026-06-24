"""DigiCamControl folder routing with Arduino remote-shutter triggering."""

from __future__ import annotations

import time
from pathlib import Path
from types import TracebackType
from typing import cast

import requests
import serial
from loguru import logger

_ARDUINO_STARTUP_GRACE_S = 2.0
_ARDUINO_POST_READY_SETTLE_S = 0.5
_SHUTTER_PROTOCOL_VERSION = "shutter-v2"
_SHUTTER_COMMAND_RETRIES = 4
_SHUTTER_RETRY_DELAY_S = 0.2


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
        self._command_counter = 0
        self._log = logger.bind(component="camera")

    def __enter__(self) -> DigiCamArduinoCamera:
        self._serial = serial.Serial(
            self._shutter_port,
            baudrate=self._shutter_baudrate,
            timeout=self._shutter_read_timeout_s,
            write_timeout=self._shutter_read_timeout_s,
        )
        self._wait_until_ready()
        time.sleep(_ARDUINO_POST_READY_SETTLE_S)
        self._clear_input_buffer()
        self._ping()
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

    def _clear_input_buffer(self) -> None:
        if self._serial is None:
            raise RuntimeError("camera shutter serial port is not open")
        self._serial.reset_input_buffer()

    def _next_command_id(self) -> str:
        self._command_counter += 1
        return f"cmd{self._command_counter:06d}"

    def _read_status_line(self, *, deadline: float, context: str) -> str:
        if self._serial is None:
            raise RuntimeError("camera shutter serial port is not open")
        ignored: list[str] = []
        while True:
            remaining_s = deadline - time.monotonic()
            if remaining_s <= 0:
                detail = f"; ignored: {ignored}" if ignored else ""
                raise TimeoutError(f"timed out waiting for Arduino {context}{detail}")
            self._serial.timeout = remaining_s
            raw = cast(bytes, self._serial.readline())
            if not raw:
                detail = f"; ignored: {ignored}" if ignored else ""
                raise TimeoutError(f"timed out waiting for Arduino {context}{detail}")
            response = raw.decode("ascii", errors="replace").strip()
            if not response:
                continue
            if response.startswith(("OK", "ERR")):
                return response
            ignored.append(response)
            self._log.debug("ignoring Arduino shutter serial line: {}", response)

    def _wait_until_ready(self) -> None:
        if self._serial is None:
            raise RuntimeError("camera shutter serial port is not open")
        deadline = time.monotonic() + _ARDUINO_STARTUP_GRACE_S
        original_timeout = self._serial.timeout
        ignored: list[str] = []
        try:
            while True:
                remaining_s = deadline - time.monotonic()
                if remaining_s <= 0:
                    detail = f"; ignored: {ignored}" if ignored else ""
                    raise TimeoutError(
                        "timed out waiting for Arduino READY shutter-v2"
                        f"{detail}; upload the v2 shutter sketch"
                    )
                self._serial.timeout = max(0.0, min(0.1, remaining_s))
                raw = cast(bytes, self._serial.readline())
                if not raw:
                    continue
                line = raw.decode("ascii", errors="replace").strip()
                if not line:
                    continue
                if line == f"READY {_SHUTTER_PROTOCOL_VERSION}":
                    return
                ignored.append(line)
                self._log.debug("Arduino shutter startup line: {}", line)
        finally:
            self._serial.timeout = original_timeout

    def _ping(self) -> None:
        self._send_nonce_command(verb="ping")

    def _send_nonce_command(self, *, verb: str, arg: str | None = None) -> str:
        response: str | None = None
        for attempt in range(_SHUTTER_COMMAND_RETRIES + 1):
            command_id = self._next_command_id()
            command = f"{verb} {command_id}" if arg is None else f"{verb} {arg} {command_id}"
            self._clear_input_buffer()
            self._write_line(command)
            deadline = time.monotonic() + self._shutter_read_timeout_s
            while True:
                response = self._read_status_line(
                    deadline=deadline,
                    context=f"{verb} response for {command_id}",
                )
                if response.startswith(f"OK {verb} {command_id}"):
                    return response
                if response.startswith(f"OK {verb} "):
                    self._log.debug("ignoring stale Arduino {} response: {}", verb, response)
                    continue
                break
            if response.startswith("ERR") and attempt < _SHUTTER_COMMAND_RETRIES:
                self._log.warning(
                    "Arduino {} command failed on attempt {}/{}: {}",
                    verb,
                    attempt + 1,
                    _SHUTTER_COMMAND_RETRIES + 1,
                    response,
                )
                time.sleep(_SHUTTER_RETRY_DELAY_S)
                continue
            break

        if response is None:
            raise RuntimeError(f"Arduino shutter did not return a {verb} response")
        if response.startswith("ERR"):
            raise RuntimeError(f"Arduino shutter error: {response}")
        raise RuntimeError(f"unexpected Arduino {verb} response: {response}")

    def set_output_folder(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        self._get({"slc": "set", "param1": "session.folder", "param2": str(folder)})
        self._log.info("camera folder set to {}", folder)

    def trigger_capture(self) -> None:
        self._send_nonce_command(verb="shoot", arg=str(self._shutter_pulse_ms))

    def start_continuous_capture(self) -> None:
        self._send_nonce_command(verb="press")

    def stop_continuous_capture(self) -> None:
        self._send_nonce_command(verb="release")
