"""Oscilloscope worker thread."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from loguru import logger

from droplet_lab.devices.base import Oscilloscope
from droplet_lab.state import ExperimentState, ExperimentStateSnapshot
from droplet_lab.storage import (
    ExperimentDirectory,
    OscilloscopeRow,
    RotatingCsvWriter,
    combo_folder_name,
    utc_now_iso,
)


class ScopeWorker:
    def __init__(
        self,
        *,
        scope: Oscilloscope,
        state: ExperimentState,
        stop_event: threading.Event,
        error_event: threading.Event,
        log_interval_s: float,
        vibrometer_factor_um_per_v: float,
        experiment_dir: ExperimentDirectory,
    ) -> None:
        self._scope = scope
        self._state = state
        self._stop = stop_event
        self._error = error_event
        self._interval = log_interval_s
        self._factor = vibrometer_factor_um_per_v
        self._exp = experiment_dir
        self._log = logger.bind(component="scope")

    def run(self) -> None:
        start = time.monotonic()
        next_log = start
        writer = RotatingCsvWriter(OscilloscopeRow)
        current_combo: int | None = None
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                snap = self._state.snapshot()
                # Rotate the output file as soon as the combo index advances,
                # regardless of the log interval — guarantees one file per combo.
                if snap.combo_index is not None and snap.combo_index != current_combo:
                    current_combo = snap.combo_index
                    folder = self._combo_folder(snap)
                    writer.open_in(folder, "oscilloscope.csv")
                if now >= next_log:
                    if writer.is_open:
                        m = self._scope.measure()
                        p2p = m.vpp_v * self._factor if m.vpp_v is not None else None
                        writer.write(
                            OscilloscopeRow(
                                timestamp_utc=utc_now_iso(),
                                elapsed_s=round(now - start, 3),
                                combo_index=snap.combo_index,
                                set_speed_rpm=snap.set_speed_rpm,
                                set_frequency_hz=snap.set_frequency_hz,
                                set_amplitude_vpp=snap.set_amplitude_vpp,
                                frequency_hz=m.frequency_hz,
                                vpp_v=m.vpp_v,
                                p2p_displacement_um=p2p,
                                ch2_vrms_dc_v=m.ch2_vrms_dc_v,
                                ch3_vrms_dc_v=m.ch3_vrms_dc_v,
                            )
                        )
                    next_log = now + self._interval
                time.sleep(0.02)
        except Exception:
            self._log.exception("scope worker crashed")
            self._error.set()
        finally:
            writer.close()
            self._log.info("scope worker finished")

    def _combo_folder(self, snap: ExperimentStateSnapshot) -> Path:
        assert snap.combo_index is not None
        assert snap.set_speed_rpm is not None
        assert snap.set_frequency_hz is not None
        assert snap.set_amplitude_vpp is not None
        return self._exp.steps_dir / combo_folder_name(
            snap.combo_index, snap.set_speed_rpm, snap.set_frequency_hz, snap.set_amplitude_vpp
        )
