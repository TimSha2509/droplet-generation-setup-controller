from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from droplet_lab.devices.camera_arduino import DigiCamArduinoCamera


def _ok_response() -> MagicMock:
    r = MagicMock()
    r.raise_for_status = MagicMock()
    return r


def _serial_with_response(response: bytes) -> MagicMock:
    ser = MagicMock()
    ser.readline.return_value = response
    return ser


def test_set_output_folder_uses_digicam_session_folder(tmp_path: Path) -> None:
    serial_port = _serial_with_response(b"OK shoot 300 ms\n")
    with (
        patch("droplet_lab.devices.camera_arduino.serial.Serial", return_value=serial_port),
        patch("droplet_lab.devices.camera_arduino.requests.get", return_value=_ok_response()) as get,
        DigiCamArduinoCamera(shutter_port="COM7") as cam,
    ):
        cam.set_output_folder(tmp_path / "images")

    calls = [c.kwargs.get("params") for c in get.call_args_list]
    assert any(
        params and params.get("slc") == "set" and params.get("param1") == "session.folder"
        for params in calls
    )


def test_trigger_capture_writes_shoot_command_and_accepts_ok() -> None:
    serial_port = _serial_with_response(b"OK shoot 450 ms\n")
    with (
        patch("droplet_lab.devices.camera_arduino.serial.Serial", return_value=serial_port),
        DigiCamArduinoCamera(shutter_port="COM7", shutter_pulse_ms=450) as cam,
    ):
        cam.trigger_capture()

    assert serial_port.write.call_args_list[0].args == (b"shoot 450\n",)
    assert serial_port.write.call_args_list[-1].args == (b"release\n",)
    serial_port.close.assert_called_once()


def test_trigger_capture_ignores_startup_banner_before_ok() -> None:
    serial_port = MagicMock()
    serial_port.readline.side_effect = [
        b"Nikon shutter controller ready.\n",
        b"Commands: shoot, press, release, bulb_on, bulb_off\n",
        b"OK shoot 300 ms\n",
    ]
    with (
        patch("droplet_lab.devices.camera_arduino.serial.Serial", return_value=serial_port),
        DigiCamArduinoCamera(shutter_port="COM7") as cam,
    ):
        cam.trigger_capture()

    assert serial_port.write.call_args_list[0].args == (b"shoot 300\n",)


def test_trigger_capture_raises_on_timeout() -> None:
    serial_port = _serial_with_response(b"")
    with (
        patch("droplet_lab.devices.camera_arduino.serial.Serial", return_value=serial_port),
        DigiCamArduinoCamera(shutter_port="COM7") as cam,
        pytest.raises(TimeoutError),
    ):
        cam.trigger_capture()


def test_trigger_capture_raises_on_error_response() -> None:
    serial_port = _serial_with_response(b"ERR unknown command\n")
    with (
        patch("droplet_lab.devices.camera_arduino.serial.Serial", return_value=serial_port),
        DigiCamArduinoCamera(shutter_port="COM7") as cam,
        pytest.raises(RuntimeError, match="ERR unknown command"),
    ):
        cam.trigger_capture()
