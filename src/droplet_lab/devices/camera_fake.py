"""In-memory camera simulator that writes empty placeholder files.

Configurable failure injection (``fail_after_triggers``, ``hang_after_triggers``)
lets integration tests exercise watchdog and error paths.
"""

from __future__ import annotations

import time
from pathlib import Path
from types import TracebackType


class FakeCamera:
    def __init__(
        self,
        *,
        fail_after_triggers: int | None = None,
        hang_after_triggers: int | None = None,
        hang_seconds: float = 0.0,
    ) -> None:
        self._folder: Path | None = None
        self._counter = 0
        self._open = False
        self._fail_after = fail_after_triggers
        self._hang_after = hang_after_triggers
        self._hang_seconds = hang_seconds

    def __enter__(self) -> "FakeCamera":
        self._open = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._open = False

    def set_output_folder(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        self._folder = folder
        self._counter = 0

    def trigger_capture(self) -> None:
        if self._folder is None:
            raise RuntimeError("set_output_folder() must be called first")
        if self._fail_after is not None and self._counter >= self._fail_after:
            raise RuntimeError("injected failure (FakeCamera)")
        if self._hang_after is not None and self._counter >= self._hang_after:
            time.sleep(self._hang_seconds)
        self._counter += 1
        path = self._folder / f"FAKE_{self._counter:04d}.NEF"
        path.write_bytes(b"")
