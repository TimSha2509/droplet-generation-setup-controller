from unittest.mock import MagicMock, patch

from droplet_lab.devices.scale_sartorius import SartoriusScale


def test_open_close() -> None:
    fake = MagicMock()
    with patch("droplet_lab.devices.scale_sartorius.serial.Serial", return_value=fake):
        with SartoriusScale(port="COM5"):
            pass
        fake.close.assert_called_once()


def test_read_weight_parses_print_line() -> None:
    fake = MagicMock()
    fake.readline.return_value = b"+   12.345 g\r\n"
    with patch("droplet_lab.devices.scale_sartorius.serial.Serial", return_value=fake):
        with SartoriusScale(port="COM5") as scale:
            assert scale.read_weight_g() == 12.345


def test_read_weight_returns_none_on_garbage() -> None:
    fake = MagicMock()
    fake.readline.return_value = b"???\r\n"
    with patch("droplet_lab.devices.scale_sartorius.serial.Serial", return_value=fake):
        with SartoriusScale(port="COM5") as scale:
            assert scale.read_weight_g() is None
