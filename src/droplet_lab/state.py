"""Status enums and the shared ExperimentState dataclass."""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from enum import StrEnum


class ExperimentStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


class StepStatus(StrEnum):
    PLANNED = "planned"
    STABILIZING = "stabilizing"
    IMAGING = "imaging"
    COMPLETED = "completed"
    COMPLETED_NO_IMAGING = "completed_no_imaging"
    CAMERA_TIMEOUT = "camera_timeout"
    CAMERA_FAILED = "camera_failed"
    ABORTED = "aborted"


class CameraStatus(StrEnum):
    NOT_STARTED = "not_started"
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


@dataclass(frozen=True, slots=True)
class ExperimentStateSnapshot:
    """Immutable point-in-time view of ExperimentState (safe to share across threads)."""

    combo_index: int | None = None
    set_speed_rpm: int | None = None
    set_frequency_hz: float | None = None
    set_amplitude_vpp: float | None = None


class ExperimentState:
    """Thread-safe holder for the currently active sweep combination.

    Workers read this every measurement to tag rows with the correct combo
    (index, rpm, freq, amp). The orchestrator updates it on every combination
    transition.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot = ExperimentStateSnapshot()

    @property
    def combo_index(self) -> int | None:
        with self._lock:
            return self._snapshot.combo_index

    @property
    def set_speed_rpm(self) -> int | None:
        with self._lock:
            return self._snapshot.set_speed_rpm

    @property
    def set_frequency_hz(self) -> float | None:
        with self._lock:
            return self._snapshot.set_frequency_hz

    @property
    def set_amplitude_vpp(self) -> float | None:
        with self._lock:
            return self._snapshot.set_amplitude_vpp

    def update(
        self,
        *,
        combo_index: int,
        set_speed_rpm: int,
        set_frequency_hz: float,
        set_amplitude_vpp: float,
    ) -> None:
        with self._lock:
            self._snapshot = replace(
                self._snapshot,
                combo_index=combo_index,
                set_speed_rpm=set_speed_rpm,
                set_frequency_hz=set_frequency_hz,
                set_amplitude_vpp=set_amplitude_vpp,
            )

    def snapshot(self) -> ExperimentStateSnapshot:
        with self._lock:
            return self._snapshot
