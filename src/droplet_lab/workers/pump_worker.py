"""Pump worker thread.

Continuously logs pump telemetry to the current combo's ``pump.csv`` and
consumes ``SetSpeedCommand`` messages from the orchestrator's queue. Rotates
the output file whenever ``ExperimentState.combo_index`` advances. Stops
cleanly on ``stop_event``; signals ``error_event`` on hardware failure.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from droplet_lab.devices.base import Pump
from droplet_lab.state import ExperimentState, ExperimentStateSnapshot
from droplet_lab.storage import (
    ExperimentDirectory,
    PumpRow,
    RotatingCsvWriter,
    combo_folder_name,
    utc_now_iso,
)


@dataclass(frozen=True, slots=True)
class SetSpeedCommand:
    rpm: int


class PumpWorker:
    def __init__(
        self,
        *,
        pump: Pump,
        state: ExperimentState,
        command_queue: queue.Queue[SetSpeedCommand],
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
        writer = RotatingCsvWriter(PumpRow)
        current_combo: int | None = None
        try:
            while not self._stop.is_set():
                try:
                    cmd = self._queue.get_nowait()
                except queue.Empty:
                    cmd = None
                if cmd is not None:
                    self._pump.set_speed(cmd.rpm)
                    self._log.info("set speed -> {} rpm", cmd.rpm)

                now = time.monotonic()
                snap = self._state.snapshot()
                # Rotate the output file as soon as the combo index advances,
                # regardless of the log interval — guarantees one file per combo.
                if snap.combo_index is not None and snap.combo_index != current_combo:
                    current_combo = snap.combo_index
                    folder = self._combo_folder(snap)
                    writer.open_in(folder, "pump.csv")
                if now >= next_log:
                    if writer.is_open:
                        writer.write(
                            PumpRow(
                                timestamp_utc=utc_now_iso(),
                                elapsed_s=round(now - start, 3),
                                combo_index=snap.combo_index,
                                set_speed_rpm=snap.set_speed_rpm,
                                set_frequency_hz=snap.set_frequency_hz,
                                set_amplitude_vpp=snap.set_amplitude_vpp,
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
            writer.close()
            try:
                self._pump.stop()
            except Exception:
                self._log.exception("failed to stop pump on shutdown")
            self._log.info("pump worker finished")

    def _combo_folder(self, snap: ExperimentStateSnapshot) -> Path:
        # Caller guarantees combo_index is non-None; orchestrator updates all four
        # fields atomically, so the others are non-None too.
        return self._exp.steps_dir / combo_folder_name(
            snap.combo_index,  # type: ignore[arg-type]
            snap.set_speed_rpm,  # type: ignore[arg-type]
            snap.set_frequency_hz,  # type: ignore[arg-type]
            snap.set_amplitude_vpp,  # type: ignore[arg-type]
        )
