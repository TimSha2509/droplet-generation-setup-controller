"""DigiCamControl HTTP client.

DigiCamControl exposes an HTTP server (default port 5513). Requests are
URL-parameterised commands; ``slc=set`` writes a property, ``slc=capture``
fires the shutter.

Reference: https://digicamcontrol.com/doc/userguide/web
"""

from __future__ import annotations

from pathlib import Path
from types import TracebackType

import requests
from loguru import logger


class DigiCamCamera:
    def __init__(
        self,
        *,
        url: str = "http://localhost:5513",
        request_timeout_s: float = 10.0,
    ) -> None:
        self._url = url
        self._timeout = request_timeout_s
        self._open = False
        self._log = logger.bind(component="camera")

    def __enter__(self) -> DigiCamCamera:
        self._open = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._open = False

    def _get(self, params: dict[str, str]) -> None:
        response = requests.get(self._url, params=params, timeout=self._timeout)
        response.raise_for_status()

    def set_output_folder(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        self._get({"slc": "set", "param1": "session.folder", "param2": str(folder)})
        self._log.info("camera folder set to {}", folder)

    def trigger_capture(self) -> None:
        self._get({"slc": "capture", "param1": "", "param2": ""})
