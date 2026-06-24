import threading
import time
from pathlib import Path

from droplet_lab.devices.camera_fake import FakeCamera
from droplet_lab.workers.camera_worker import (
    CameraResultStatus,
    run_camera_capture,
)


class ContinuousFakeCamera:
    def __init__(self) -> None:
        self.folder: Path | None = None
        self.started = 0
        self.stopped = 0
        self.triggered = 0

    def __enter__(self) -> "ContinuousFakeCamera":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def set_output_folder(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        self.folder = folder

    def trigger_capture(self) -> None:
        self.triggered += 1

    def start_continuous_capture(self) -> None:
        self.started += 1

    def stop_continuous_capture(self) -> None:
        self.stopped += 1


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


def test_continuous_camera_presses_once_and_releases_at_end(tmp_path: Path) -> None:
    cam = ContinuousFakeCamera()
    result = run_camera_capture(
        camera=cam,
        output_folder=tmp_path,
        interval_s=0.01,
        duration_s=0.05,
        latency_tolerance_s=0.0,
        stop_event=threading.Event(),
    )

    assert result.status is CameraResultStatus.COMPLETED
    assert result.captures == 1
    assert cam.started == 1
    assert cam.stopped == 1
    assert cam.triggered == 0


def test_continuous_camera_releases_on_stop_event(tmp_path: Path) -> None:
    cam = ContinuousFakeCamera()
    stop = threading.Event()

    def trip() -> None:
        time.sleep(0.03)
        stop.set()

    thread = threading.Thread(target=trip)
    thread.start()
    result = run_camera_capture(
        camera=cam,
        output_folder=tmp_path,
        interval_s=0.01,
        duration_s=10.0,
        latency_tolerance_s=0.0,
        stop_event=stop,
    )
    thread.join(timeout=1.0)

    assert result.status is CameraResultStatus.ABORTED
    assert cam.started == 1
    assert cam.stopped == 1
