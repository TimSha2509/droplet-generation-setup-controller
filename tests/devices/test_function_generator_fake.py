import pytest

from droplet_lab.devices.function_generator_fake import FakeFunctionGenerator


def test_records_calls_in_order() -> None:
    with FakeFunctionGenerator() as fg:
        fg.set_sine()
        fg.set_frequency_hz(20.0)
        fg.set_amplitude_vpp(3.0)
        fg.enable_output(True)
        fg.set_amplitude_vpp(5.0)
        fg.enable_output(False)
    assert fg.calls == [
        ("set_sine",),
        ("set_frequency_hz", 20.0),
        ("set_amplitude_vpp", 3.0),
        ("enable_output", True),
        ("set_amplitude_vpp", 5.0),
        ("enable_output", False),
    ]


def test_state_reflects_last_setting() -> None:
    with FakeFunctionGenerator() as fg:
        fg.set_sine()
        fg.set_frequency_hz(25.0)
        fg.set_amplitude_vpp(5.0)
        fg.enable_output(True)
        assert fg.is_sine is True
        assert fg.frequency_hz == 25.0
        assert fg.amplitude_vpp == 5.0
        assert fg.output_on is True


def test_exit_resets_output_on_for_safety() -> None:
    fg = FakeFunctionGenerator()
    with fg:
        fg.enable_output(True)
        assert fg.output_on is True
    assert fg.output_on is False


def test_amplitude_above_limit_raises() -> None:
    fg = FakeFunctionGenerator()
    with fg:
        with pytest.raises(ValueError, match="exceeds hardware limit"):
            fg.set_amplitude_vpp(9.6)
