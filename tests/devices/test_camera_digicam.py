from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from droplet_lab.devices.camera_digicam import DigiCamCamera


def _ok_response() -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.text = "OK"
    r.raise_for_status = MagicMock()
    return r


def test_set_output_folder_calls_session_folder() -> None:
    with patch("droplet_lab.devices.camera_digicam.requests.get",
               return_value=_ok_response()) as get:
        with DigiCamCamera(url="http://localhost:5513") as cam:
            cam.set_output_folder(Path("C:/data/step_01"))
        # First call after enter is the set; assert it carries session.folder
        calls = [c.kwargs.get("params") for c in get.call_args_list]
        assert any(
            params and params.get("slc") == "set" and params.get("param1") == "session.folder"
            for params in calls
        )


def test_trigger_capture_calls_capture_endpoint() -> None:
    with patch("droplet_lab.devices.camera_digicam.requests.get",
               return_value=_ok_response()) as get:
        with DigiCamCamera(url="http://localhost:5513") as cam:
            cam.set_output_folder(Path("C:/data/step_01"))
            cam.trigger_capture()
        calls = [c.kwargs.get("params") for c in get.call_args_list]
        assert any(p and p.get("slc") == "capture" for p in calls)


def test_http_error_raises(tmp_path: Path) -> None:
    ok = MagicMock()
    ok.raise_for_status = MagicMock()
    bad = MagicMock()
    bad.raise_for_status.side_effect = RuntimeError("HTTP 500")
    with patch("droplet_lab.devices.camera_digicam.requests.get",
               side_effect=[ok, bad]):
        with DigiCamCamera(url="http://localhost:5513") as cam:
            cam.set_output_folder(tmp_path / "step")
            with pytest.raises(RuntimeError):
                cam.trigger_capture()
