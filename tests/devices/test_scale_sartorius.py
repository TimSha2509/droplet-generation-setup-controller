from unittest.mock import MagicMock, patch

import serial

from droplet_lab.devices.scale_sartorius import SartoriusScale


def test_enter_opens_serial_with_7e1_at_1200_baud_xonxoff() -> None:
    fake = MagicMock()
    fake.readline.return_value = b"+ 12.345 g\r\n"
    with (
        patch("droplet_lab.devices.scale_sartorius.serial.Serial", return_value=fake) as ctor,
        SartoriusScale(port="COM3"),
    ):
        pass
    ctor.assert_called_once_with(
        port="COM3",
        baudrate=1200,
        bytesize=serial.SEVENBITS,
        parity=serial.PARITY_EVEN,
        stopbits=serial.STOPBITS_ONE,
        timeout=1.0,
        xonxoff=True,
    )


def test_open_close() -> None:
    fake = MagicMock()
    with patch("droplet_lab.devices.scale_sartorius.serial.Serial", return_value=fake):
        with SartoriusScale(port="COM5"):
            pass
        fake.close.assert_called_once()


def test_read_weight_parses_print_line() -> None:
    fake = MagicMock()
    fake.readline.return_value = b"+   648.05 g\r\n"
    with (
        patch("droplet_lab.devices.scale_sartorius.serial.Serial", return_value=fake),
        SartoriusScale(port="COM5") as scale,
    ):
        assert scale.read_weight_g() == 648.05
    fake.reset_input_buffer.assert_called_once()


def test_read_weight_discards_first_line_after_flush() -> None:
    fake = MagicMock()
    fake.readline.side_effect = [b"48.05 g\r\n", b"+   648.05 g\r\n"]
    with (
        patch("droplet_lab.devices.scale_sartorius.serial.Serial", return_value=fake),
        SartoriusScale(port="COM5", read_window_s=0.25) as scale,
    ):
        assert scale.read_weight_g() == 648.05


def test_read_weight_skips_invalid_lines_until_valid() -> None:
    fake = MagicMock()
    fake.readline.side_effect = [b"", b"???\r\n", b"+   12.345 g\r\n"]
    with (
        patch("droplet_lab.devices.scale_sartorius.serial.Serial", return_value=fake),
        SartoriusScale(port="COM5", read_window_s=0.25) as scale,
    ):
        assert scale.read_weight_g() == 12.345


def test_read_weight_rejects_embedded_numbers_until_valid() -> None:
    fake = MagicMock()
    fake.readline.side_effect = [b"", b"status: 648.05 g\r\n", b"+   648.05 g\r\n"]
    with (
        patch("droplet_lab.devices.scale_sartorius.serial.Serial", return_value=fake),
        SartoriusScale(port="COM5", read_window_s=0.25) as scale,
    ):
        assert scale.read_weight_g() == 648.05


def test_read_weight_parses_sign_with_internal_spaces() -> None:
    fake = MagicMock()
    fake.readline.return_value = b"-   12.345 g\r\n"
    with (
        patch("droplet_lab.devices.scale_sartorius.serial.Serial", return_value=fake),
        SartoriusScale(port="COM5") as scale,
    ):
        assert scale.read_weight_g() == -12.345


def test_read_weight_returns_none_on_garbage() -> None:
    fake = MagicMock()
    fake.readline.return_value = b"???\r\n"
    with (
        patch("droplet_lab.devices.scale_sartorius.serial.Serial", return_value=fake),
        SartoriusScale(port="COM5", read_window_s=0.01) as scale,
    ):
        assert scale.read_weight_g() is None
