"""Scale worker thread (optional — only spawned if the scale is enabled)."""

from __future__ import annotations

import threading
import time

from loguru import logger

from droplet_lab.devices.base import Scale
from droplet_lab.state import ExperimentState
from droplet_lab.storage import ExperimentDirectory, ScaleRow, utc_now_iso


class ScaleWorker:
    def __init__(
        self,
        *,
        scale: Scale,
        state: ExperimentState,
        stop_event: threading.Event,
        error_event: threading.Event,
        log_interval_s: float,
        experiment_dir: ExperimentDirectory,
    ) -> None:
        self._scale = scale
        self._state = state
        self._stop = stop_event
        self._error = error_event
        self._interval = log_interval_s
        self._exp = experiment_dir
        self._log = logger.bind(component="scale")

    def run(self) -> None:
        start = time.monotonic()
        next_log = start
        try:
            with self._exp.open_scale_csv() as writer:
                while not self._stop.is_set():
                    now = time.monotonic()
                    if now >= next_log:
                        snap = self._state.snapshot()
                        writer.write(
                            ScaleRow(
                                timestamp_utc=utc_now_iso(),
                                elapsed_s=round(now - start, 3),
                                step_index=snap.step_index,
                                set_speed_rpm=snap.set_speed_rpm,
                                weight_g=self._scale.read_weight_g(),
                            )
                        )
                        next_log = now + self._interval
                    time.sleep(0.02)
        except Exception:
            self._log.exception("scale worker crashed")
            self._error.set()
        finally:
            self._log.info("scale worker finished")
