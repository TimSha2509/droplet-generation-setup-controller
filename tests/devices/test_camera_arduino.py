from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from droplet_lab.devices.camera_arduino import DigiCamArduinoCamera


@pytest.fixture(autouse=True)
def _fast_handshake() -> Iterator[None]:
    with (
        patch("droplet_lab.devices.camera_arduino._ARDUINO_POST_READY_SETTLE_S", 0.0),
        patch("droplet_lab.devices.camera_arduino.time.sleep"),
    ):
        yield


def _ok_response() -> MagicMock:
    r = MagicMock()
    r.raise_for_status = MagicMock()
    return r


def _v2_serial(*capture_responses: bytes) -> MagicMock:
    ser = MagicMock()
    ser.readline.side_effect = [
        b"READY shutter-v2\n",
        b"OK ping cmd000001\n",
        *capture_responses,
    ]
    return ser


def test_set_output_folder_uses_digicam_session_folder(tmp_path: Path) -> None:
    serial_port = _v2_serial()
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


def test_enter_waits_for_ready_and_pings_controller() -> None:
    serial_port = _v2_serial()
    with (
        patch("droplet_lab.devices.camera_arduino.serial.Serial", return_value=serial_port),
        DigiCamArduinoCamera(shutter_port="COM7"),
    ):
        pass

    assert serial_port.write.call_args_list[0].args == (b"ping cmd000001\n",)
    assert serial_port.write.call_args_list[-1].args == (b"release\n",)
    serial_port.close.assert_called_once()


def test_enter_ignores_noise_and_blank_lines_before_ready() -> None:
    serial_port = MagicMock()
    serial_port.readline.side_effect = [
        b"\n",
        b"Nikon shutter controller ready.\n",
        b"READY shutter-v2\n",
        b"OK ping cmd000001\n",
    ]
    with (
        patch("droplet_lab.devices.camera_arduino.serial.Serial", return_value=serial_port),
        DigiCamArduinoCamera(shutter_port="COM7"),
    ):
        pass

    assert serial_port.write.call_args_list[0].args == (b"ping cmd000001\n",)


def test_enter_requires_matching_ping_response() -> None:
    serial_port = MagicMock()
    serial_port.readline.side_effect = [
        b"READY shutter-v2\n",
        b"OK ping old\n",
        b"",
    ]
    with (
        patch("droplet_lab.devices.camera_arduino.serial.Serial", return_value=serial_port),
        pytest.raises(TimeoutError, match="ping response"),
        DigiCamArduinoCamera(shutter_port="COM7", shutter_read_timeout_s=0.01),
    ):
        pass


def test_enter_retries_corrupted_first_ping_response() -> None:
    serial_port = MagicMock()
    serial_port.readline.side_effect = [
        b"READY shutter-v2\n",
        b"ERR unknown command p\xef\xbf\xbd\xef\xbf\xbd\xef\xbf\xbdcmd000001\n",
        b"OK ping cmd000002\n",
    ]
    with (
        patch("droplet_lab.devices.camera_arduino.serial.Serial", return_value=serial_port),
        DigiCamArduinoCamera(shutter_port="COM7"),
    ):
        pass

    assert serial_port.write.call_args_list[0].args == (b"ping cmd000001\n",)
    assert serial_port.write.call_args_list[1].args == (b"ping cmd000002\n",)


def test_trigger_capture_writes_nonce_shoot_command_and_accepts_matching_ok() -> None:
    serial_port = _v2_serial(b"OK shoot cmd000002 450 ms\n")
    with (
        patch("droplet_lab.devices.camera_arduino.serial.Serial", return_value=serial_port),
        DigiCamArduinoCamera(shutter_port="COM7", shutter_pulse_ms=450) as cam,
    ):
        cam.trigger_capture()

    assert serial_port.write.call_args_list[1].args == (b"shoot 450 cmd000002\n",)


def test_trigger_capture_ignores_stale_shoot_response_before_matching_ok() -> None:
    serial_port = _v2_serial(
        b"OK shoot old 300 ms\n",
        b"OK shoot cmd000002 300 ms\n",
    )
    with (
        patch("droplet_lab.devices.camera_arduino.serial.Serial", return_value=serial_port),
        DigiCamArduinoCamera(shutter_port="COM7") as cam,
    ):
        cam.trigger_capture()

    assert serial_port.write.call_args_list[1].args == (b"shoot 300 cmd000002\n",)


def test_trigger_capture_retries_on_unknown_command_then_succeeds() -> None:
    serial_port = _v2_serial(
        b"ERR unknown command shoot 300 cmd000002\n",
        b"OK shoot cmd000003 300 ms\n",
    )
    with (
        patch("droplet_lab.devices.camera_arduino.serial.Serial", return_value=serial_port),
        DigiCamArduinoCamera(shutter_port="COM7") as cam,
    ):
        cam.trigger_capture()

    assert serial_port.write.call_args_list[1].args == (b"shoot 300 cmd000002\n",)
    assert serial_port.write.call_args_list[2].args == (b"shoot 300 cmd000003\n",)


def test_start_and_stop_continuous_capture_use_press_release_commands() -> None:
    serial_port = _v2_serial(
        b"OK press cmd000002\n",
        b"OK release cmd000003\n",
    )
    with (
        patch("droplet_lab.devices.camera_arduino.serial.Serial", return_value=serial_port),
        DigiCamArduinoCamera(shutter_port="COM7") as cam,
    ):
        cam.start_continuous_capture()
        cam.stop_continuous_capture()

    assert serial_port.write.call_args_list[1].args == (b"press cmd000002\n",)
    assert serial_port.write.call_args_list[2].args == (b"release cmd000003\n",)


def test_trigger_capture_raises_when_unknown_command_persists() -> None:
    serial_port = _v2_serial(
        b"ERR unknown command shoot 300 cmd000002\n",
        b"ERR unknown command shoot 300 cmd000003\n",
        b"ERR unknown command shoot 300 cmd000004\n",
        b"ERR unknown command shoot 300 cmd000005\n",
        b"ERR unknown command shoot 300 cmd000006\n",
    )
    with (
        patch("droplet_lab.devices.camera_arduino.serial.Serial", return_value=serial_port),
        DigiCamArduinoCamera(shutter_port="COM7") as cam,
        pytest.raises(RuntimeError, match="ERR unknown command"),
    ):
        cam.trigger_capture()

    assert serial_port.write.call_args_list[1].args == (b"shoot 300 cmd000002\n",)
    assert serial_port.write.call_args_list[5].args == (b"shoot 300 cmd000006\n",)


def test_trigger_capture_timeout_still_fails_clearly() -> None:
    serial_port = _v2_serial(b"")
    with (
        patch("droplet_lab.devices.camera_arduino.serial.Serial", return_value=serial_port),
        DigiCamArduinoCamera(shutter_port="COM7", shutter_read_timeout_s=0.01) as cam,
        pytest.raises(TimeoutError, match="shoot response"),
    ):
        cam.trigger_capture()
