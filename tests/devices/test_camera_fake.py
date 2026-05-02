from pathlib import Path

import pytest

from droplet_lab.devices.camera_fake import FakeCamera


def test_satisfies_protocol() -> None:
    from droplet_lab.devices.base import Camera
    c: Camera = FakeCamera()
    assert c is not None


def test_trigger_writes_file(tmp_path: Path) -> None:
    with FakeCamera() as cam:
        cam.set_output_folder(tmp_path)
        cam.trigger_capture()
        cam.trigger_capture()
    files = sorted(tmp_path.glob("*.NEF"))
    assert len(files) == 2
    assert files[0].name == "FAKE_0001.NEF"
    assert files[1].name == "FAKE_0002.NEF"


def test_trigger_without_folder_raises() -> None:
    with FakeCamera() as cam:
        with pytest.raises(RuntimeError):
            cam.trigger_capture()


def test_can_be_configured_to_fail(tmp_path: Path) -> None:
    cam = FakeCamera(fail_after_triggers=2)
    with cam:
        cam.set_output_folder(tmp_path)
        cam.trigger_capture()
        cam.trigger_capture()
        with pytest.raises(RuntimeError, match="injected"):
            cam.trigger_capture()


def test_can_be_configured_to_hang(tmp_path: Path) -> None:
    import time
    cam = FakeCamera(hang_after_triggers=1, hang_seconds=0.2)
    with cam:
        cam.set_output_folder(tmp_path)
        cam.trigger_capture()
        start = time.monotonic()
        cam.trigger_capture()
        assert time.monotonic() - start >= 0.2
