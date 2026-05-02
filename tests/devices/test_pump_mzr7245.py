from unittest.mock import MagicMock, patch

import pytest

from droplet_lab.devices.pump_mzr7245 import MZR7245Pump


@pytest.fixture
def fake_serial() -> MagicMock:
    s = MagicMock()
    s.is_open = True
    s.read_all.return_value = b""
    return s


def test_context_manager_opens_and_closes(fake_serial: MagicMock) -> None:
    with patch("droplet_lab.devices.pump_mzr7245.serial.Serial", return_value=fake_serial):
        with MZR7245Pump(port="COM3", baudrate=9600) as pump:
            assert pump is not None
        fake_serial.close.assert_called_once()


def test_set_speed_writes_v_command(fake_serial: MagicMock) -> None:
    with patch("droplet_lab.devices.pump_mzr7245.serial.Serial", return_value=fake_serial):
        with MZR7245Pump(port="COM3") as pump:
            pump.set_speed(250)
        fake_serial.write.assert_any_call(b"V250\r")


def test_stop_writes_v0(fake_serial: MagicMock) -> None:
    with patch("droplet_lab.devices.pump_mzr7245.serial.Serial", return_value=fake_serial):
        with MZR7245Pump(port="COM3") as pump:
            pump.stop()
        fake_serial.write.assert_any_call(b"V0\r")


def test_get_actual_speed_parses_int(fake_serial: MagicMock) -> None:
    fake_serial.read_all.return_value = b"199\r\n"
    with (
        patch("droplet_lab.devices.pump_mzr7245.serial.Serial", return_value=fake_serial),
        MZR7245Pump(port="COM3") as pump,
    ):
        assert pump.get_actual_speed_rpm() == 199


def test_get_actual_speed_returns_none_on_garbage(fake_serial: MagicMock) -> None:
    fake_serial.read_all.return_value = b"???"
    with (
        patch("droplet_lab.devices.pump_mzr7245.serial.Serial", return_value=fake_serial),
        MZR7245Pump(port="COM3") as pump,
    ):
        assert pump.get_actual_speed_rpm() is None


def test_satisfies_pump_protocol(fake_serial: MagicMock) -> None:
    from droplet_lab.devices.base import Pump

    with patch("droplet_lab.devices.pump_mzr7245.serial.Serial", return_value=fake_serial):
        pump: Pump = MZR7245Pump(port="COM3")
        assert pump is not None
