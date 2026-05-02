"""Pump worker thread.

Continuously logs pump telemetry to ``pump.csv`` and consumes ``SetSpeedCommand``
messages from the orchestrator's queue. Stops cleanly when ``stop_event`` is
set; signals ``error_event`` on hardware failure.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass

from loguru import logger

from droplet_lab.devices.base import Pump
from droplet_lab.state import ExperimentState
from droplet_lab.storage import ExperimentDirectory, PumpRow, utc_now_iso


@dataclass(frozen=True, slots=True)
class SetSpeedCommand:
    rpm: int


class PumpWorker:
    def __init__(
        self,
        *,
        pump: Pump,
        state: ExperimentState,
        command_queue: "queue.Queue[SetSpeedCommand]",
        stop_event: threading.Event,
        error_event: threading.Event,
        log_interval_s: float,
        experiment_dir: ExperimentDirectory,
    ) -> None:
        self._pump = pump
        self._state = state
        self._queue = command_queue
        self._stop = stop_event
        self._error = error_event
        self._log_interval_s = log_interval_s
        self._exp = experiment_dir
        self._log = logger.bind(component="pump")

    def run(self) -> None:
        start = time.monotonic()
        next_log = start
        try:
            with self._exp.open_pump_csv() as writer:
                while not self._stop.is_set():
                    try:
                        cmd = self._queue.get_nowait()
                    except queue.Empty:
                        cmd = None
                    if cmd is not None:
                        self._pump.set_speed(cmd.rpm)
                        self._log.info("set speed -> {} rpm", cmd.rpm)

                    now = time.monotonic()
                    if now >= next_log:
                        snap = self._state.snapshot()
                        writer.write(
                            PumpRow(
                                timestamp_utc=utc_now_iso(),
                                elapsed_s=round(now - start, 3),
                                step_index=snap.step_index,
                                set_speed_rpm=snap.set_speed_rpm,
                                actual_speed_rpm=self._pump.get_actual_speed_rpm(),
                                temperature_c=self._pump.get_temperature_c(),
                            )
                        )
                        next_log = now + self._log_interval_s
                    time.sleep(0.02)
        except Exception:
            self._log.exception("pump worker crashed")
            self._error.set()
        finally:
            try:
                self._pump.stop()
            except Exception:
                self._log.exception("failed to stop pump on shutdown")
            self._log.info("pump worker finished")
