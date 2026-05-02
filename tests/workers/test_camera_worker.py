import threading
from pathlib import Path

import pytest

from droplet_lab.devices.camera_fake import FakeCamera
from droplet_lab.workers.camera_worker import (
    CameraResult,
    CameraResultStatus,
    run_camera_capture,
)


def test_completes_when_duration_elapses(tmp_path: Path) -> None:
    cam = FakeCamera()
    with cam:
        result = run_camera_capture(
            camera=cam,
            output_folder=tmp_path,
            interval_s=0.05,
            duration_s=0.2,
            latency_tolerance_s=0.05,
            stop_event=threading.Event(),
        )
    assert result.status is CameraResultStatus.COMPLETED
    assert result.captures >= 4
    assert len(list(tmp_path.glob("*.NEF"))) == result.captures


def test_aborts_on_stop_event(tmp_path: Path) -> None:
    cam = FakeCamera()
    stop = threading.Event()

    def trip() -> None:
        import time
        time.sleep(0.1)
        stop.set()

    threading.Thread(target=trip).start()
    with cam:
        result = run_camera_capture(
            camera=cam,
            output_folder=tmp_path,
            interval_s=0.05,
            duration_s=10.0,  # would normally run forever
            latency_tolerance_s=0.05,
            stop_event=stop,
        )
    assert result.status is CameraResultStatus.ABORTED


def test_marks_failed_when_capture_raises(tmp_path: Path) -> None:
    cam = FakeCamera(fail_after_triggers=2)
    with cam:
        result = run_camera_capture(
            camera=cam,
            output_folder=tmp_path,
            interval_s=0.05,
            duration_s=0.5,
            latency_tolerance_s=0.05,
            stop_event=threading.Event(),
        )
    assert result.status is CameraResultStatus.FAILED
    assert result.error is not None


def test_zero_duration_returns_no_imaging(tmp_path: Path) -> None:
    cam = FakeCamera()
    with cam:
        result = run_camera_capture(
            camera=cam,
            output_folder=tmp_path,
            interval_s=0.05,
            duration_s=0.0,
            latency_tolerance_s=0.05,
            stop_event=threading.Event(),
        )
    assert result.status is CameraResultStatus.NO_IMAGING
    assert result.captures == 0
