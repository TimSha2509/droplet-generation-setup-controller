"""Per-step camera capture loop.

Synchronous (called from the orchestrator), but checks ``stop_event`` between
captures so a Ctrl-C interrupts cleanly. Returns a ``CameraResult``; the
orchestrator interprets the status and writes step.json accordingly.

The function intentionally does not raise on capture errors - failures become
``CameraResultStatus.FAILED`` with the exception attached, so the orchestrator
can decide whether to abort the experiment.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from loguru import logger

from droplet_lab.devices.base import Camera, ContinuousCamera


class CameraResultStatus(StrEnum):
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"
    NO_IMAGING = "no_imaging"


@dataclass(frozen=True, slots=True)
class CameraResult:
    status: CameraResultStatus
    captures: int
    error: str | None = None


def run_camera_capture(
    *,
    camera: Camera,
    output_folder: Path,
    interval_s: float,
    duration_s: float,
    latency_tolerance_s: float,
    stop_event: threading.Event,
) -> CameraResult:
    log = logger.bind(component="camera")

    if duration_s <= 0:
        log.info("step has zero imaging duration, skipping capture")
        return CameraResult(status=CameraResultStatus.NO_IMAGING, captures=0)

    try:
        camera.set_output_folder(output_folder)
    except Exception as e:
        log.exception("failed to set output folder")
        return CameraResult(status=CameraResultStatus.FAILED, captures=0, error=str(e))

    if isinstance(camera, ContinuousCamera):
        return _run_continuous_camera_capture(
            camera=camera,
            duration_s=duration_s,
            latency_tolerance_s=latency_tolerance_s,
            stop_event=stop_event,
            log=log,
        )

    start = time.monotonic()
    next_capture_at = start
    captures = 0

    while True:
        now = time.monotonic()
        elapsed = now - start
        if elapsed > duration_s:
            break
        if stop_event.is_set():
            log.info("stop signal received during capture")
            return CameraResult(status=CameraResultStatus.ABORTED, captures=captures)
        if now >= next_capture_at:
            try:
                camera.trigger_capture()
            except Exception as e:
                log.exception("capture failed at frame {}", captures + 1)
                return CameraResult(
                    status=CameraResultStatus.FAILED,
                    captures=captures,
                    error=str(e),
                )
            captures += 1
            log.info("captured frame {}", captures)
            next_capture_at += interval_s
        else:
            time.sleep(0.02)

    if latency_tolerance_s > 0:
        log.debug("waiting {} s latency tolerance", latency_tolerance_s)
        # Cooperative wait
        deadline = time.monotonic() + latency_tolerance_s
        while time.monotonic() < deadline:
            if stop_event.is_set():
                return CameraResult(status=CameraResultStatus.ABORTED, captures=captures)
            time.sleep(0.02)

    return CameraResult(status=CameraResultStatus.COMPLETED, captures=captures)


def _run_continuous_camera_capture(
    *,
    camera: ContinuousCamera,
    duration_s: float,
    latency_tolerance_s: float,
    stop_event: threading.Event,
    log: object,
) -> CameraResult:
    try:
        camera.start_continuous_capture()
        log.info("continuous camera capture started")
    except Exception as e:
        log.exception("failed to start continuous camera capture")
        return CameraResult(status=CameraResultStatus.FAILED, captures=0, error=str(e))

    status = CameraResultStatus.COMPLETED
    error: str | None = None
    try:
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline:
            if stop_event.is_set():
                log.info("stop signal received during continuous capture")
                status = CameraResultStatus.ABORTED
                break
            time.sleep(0.02)
    finally:
        try:
            camera.stop_continuous_capture()
            log.info("continuous camera capture stopped")
        except Exception as e:
            log.exception("failed to stop continuous camera capture")
            status = CameraResultStatus.FAILED
            error = str(e)

    if status is CameraResultStatus.COMPLETED and latency_tolerance_s > 0:
        log.debug("waiting {} s latency tolerance", latency_tolerance_s)
        deadline = time.monotonic() + latency_tolerance_s
        while time.monotonic() < deadline:
            if stop_event.is_set():
                return CameraResult(status=CameraResultStatus.ABORTED, captures=1)
            time.sleep(0.02)

    return CameraResult(status=status, captures=1, error=error)
