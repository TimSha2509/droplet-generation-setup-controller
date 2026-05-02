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

    step_index: int | None = None
    set_speed_rpm: int | None = None


class ExperimentState:
    """Thread-safe holder for the orchestrator's currently active step + speed.

    Workers (especially the scope) read this every measurement to tag rows with
    the correct step. The orchestrator updates it on every ramp transition.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot = ExperimentStateSnapshot()

    @property
    def step_index(self) -> int | None:
        with self._lock:
            return self._snapshot.step_index

    @property
    def set_speed_rpm(self) -> int | None:
        with self._lock:
            return self._snapshot.set_speed_rpm

    def update(self, *, step_index: int, set_speed_rpm: int) -> None:
        with self._lock:
            self._snapshot = replace(
                self._snapshot,
                step_index=step_index,
                set_speed_rpm=set_speed_rpm,
            )

    def snapshot(self) -> ExperimentStateSnapshot:
        with self._lock:
            return self._snapshot
