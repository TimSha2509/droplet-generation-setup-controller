from unittest.mock import MagicMock, patch

import pytest

from droplet_lab.devices.function_generator_psg9080 import (
    MAX_AMPLITUDE_VPP,
    PSG9080Generator,
)


def _open(port="COM4", channel=1) -> tuple[PSG9080Generator, MagicMock]:
    fake_serial = MagicMock()
    fake_serial.read_all.return_value = b""
    with patch("droplet_lab.devices.function_generator_psg9080.serial.Serial", return_value=fake_serial):
        fg = PSG9080Generator(port=port, channel=channel)
        fg.__enter__()
    return fg, fake_serial


def _written(fake_serial: MagicMock) -> list[bytes]:
    return [call.args[0] for call in fake_serial.write.call_args_list]


def test_enter_opens_serial_and_sets_sine_output_off() -> None:
    fg, fake = _open(channel=1)
    sent = _written(fake)
    assert b":w11=0.\r\n" in sent
    assert b":w10=0,0.\r\n" in sent
    fg.__exit__(None, None, None)


def test_set_frequency_scales_by_1000_channel_1() -> None:
    fg, fake = _open(channel=1)
    fake.reset_mock()
    fg.set_frequency_hz(20.0)
    assert _written(fake) == [b":w13=20000,0.\r\n"]
    fg.__exit__(None, None, None)


def test_set_frequency_uses_w14_for_channel_2() -> None:
    fg, fake = _open(channel=2)
    fake.reset_mock()
    fg.set_frequency_hz(25.5)
    assert _written(fake) == [b":w14=25500,0.\r\n"]
    fg.__exit__(None, None, None)


def test_set_amplitude_scales_by_1000() -> None:
    fg, fake = _open(channel=1)
    fake.reset_mock()
    fg.set_amplitude_vpp(3.0)
    assert _written(fake) == [b":w15=3000.\r\n"]
    fg.__exit__(None, None, None)


def test_set_amplitude_above_limit_raises_and_writes_nothing() -> None:
    fg, fake = _open(channel=1)
    fake.reset_mock()
    with pytest.raises(ValueError, match="exceeds hardware limit"):
        fg.set_amplitude_vpp(9.6)
    assert _written(fake) == []
    fg.__exit__(None, None, None)


def test_enable_output_channel_1() -> None:
    fg, fake = _open(channel=1)
    fake.reset_mock()
    fg.enable_output(True)
    assert _written(fake) == [b":w10=1,0.\r\n"]
    fg.__exit__(None, None, None)


def test_enable_output_channel_2() -> None:
    fg, fake = _open(channel=2)
    fake.reset_mock()
    fg.enable_output(True)
    assert _written(fake) == [b":w10=0,1.\r\n"]
    fg.__exit__(None, None, None)


def test_exit_sets_output_off_and_closes_serial() -> None:
    fg, fake = _open(channel=1)
    fake.reset_mock()
    fg.__exit__(None, None, None)
    sent = _written(fake)
    assert b":w10=0,0.\r\n" in sent
    fake.close.assert_called_once()


def test_max_amplitude_constant_reexported() -> None:
    assert MAX_AMPLITUDE_VPP == 9.5
