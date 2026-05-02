from unittest.mock import MagicMock, patch

import pytest

from droplet_lab.devices.oscilloscope_keysight import KeysightOscilloscope


@pytest.fixture
def fake_scope() -> MagicMock:
    scope = MagicMock()
    scope.query.return_value = "1.0"
    return scope


@pytest.fixture
def fake_rm(fake_scope: MagicMock) -> MagicMock:
    rm = MagicMock()
    rm.open_resource.return_value = fake_scope
    return rm


def test_context_manager_opens_visa(fake_rm: MagicMock, fake_scope: MagicMock) -> None:
    with patch("droplet_lab.devices.oscilloscope_keysight.pyvisa.ResourceManager",
               return_value=fake_rm):
        with KeysightOscilloscope(visa_resource="USB0::INSTR") as scope:
            assert scope is not None
        fake_scope.close.assert_called_once()


def test_identify_calls_idn(fake_rm: MagicMock, fake_scope: MagicMock) -> None:
    fake_scope.query.return_value = "Keysight,DSOX,1234,A.01"
    with patch("droplet_lab.devices.oscilloscope_keysight.pyvisa.ResourceManager",
               return_value=fake_rm):
        with KeysightOscilloscope(visa_resource="USB0::INSTR") as scope:
            assert scope.identify() == "Keysight,DSOX,1234,A.01"


def test_measure_issues_expected_scpi(fake_rm: MagicMock, fake_scope: MagicMock) -> None:
    fake_scope.query.side_effect = ["199.5", "0.42", "0.51", "0.49"]
    with patch("droplet_lab.devices.oscilloscope_keysight.pyvisa.ResourceManager",
               return_value=fake_rm):
        with KeysightOscilloscope(visa_resource="USB0::INSTR") as scope:
            m = scope.measure()
    assert m.frequency_hz == 199.5
    assert m.vpp_v == 0.42
    assert m.ch2_vrms_dc_v == 0.51
    assert m.ch3_vrms_dc_v == 0.49


def test_measure_returns_none_on_invalid_value(fake_rm: MagicMock, fake_scope: MagicMock) -> None:
    fake_scope.query.side_effect = ["NaN", "garbage", "9.91E+37", "0.5"]
    with patch("droplet_lab.devices.oscilloscope_keysight.pyvisa.ResourceManager",
               return_value=fake_rm):
        with KeysightOscilloscope(visa_resource="USB0::INSTR") as scope:
            m = scope.measure()
    # Keysight scopes return 9.91e+37 for "no signal"
    assert m.frequency_hz is None
    assert m.vpp_v is None
    assert m.ch2_vrms_dc_v is None
    assert m.ch3_vrms_dc_v == 0.5
