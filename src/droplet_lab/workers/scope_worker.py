"""Oscilloscope worker thread.

Polls the scope at ``log_interval_s`` cadence; tags each row with the current
step from ``ExperimentState``; computes peak-to-peak displacement from Vpp via
the vibrometer factor.
"""

from __future__ import annotations

import threading
import time

from loguru import logger

from droplet_lab.devices.base import Oscilloscope
from droplet_lab.state import ExperimentState
from droplet_lab.storage import ExperimentDirectory, OscilloscopeRow, utc_now_iso


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
        try:
            with self._exp.open_oscilloscope_csv() as writer:
                while not self._stop.is_set():
                    now = time.monotonic()
                    if now >= next_log:
                        snap = self._state.snapshot()
                        m = self._scope.measure()
                        p2p = m.vpp_v * self._factor if m.vpp_v is not None else None
                        writer.write(
                            OscilloscopeRow(
                                timestamp_utc=utc_now_iso(),
                                elapsed_s=round(now - start, 3),
                                step_index=snap.step_index,
                                set_speed_rpm=snap.set_speed_rpm,
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
            self._log.info("scope worker finished")
