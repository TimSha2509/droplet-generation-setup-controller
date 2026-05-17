from droplet_lab.devices.oscilloscope_fake import FakeOscilloscope
from droplet_lab.state import ExperimentState


def test_satisfies_protocol() -> None:
    from droplet_lab.devices.base import Oscilloscope

    s: Oscilloscope = FakeOscilloscope(state=ExperimentState(), seed=0)
    assert s is not None


def test_identify_returns_label() -> None:
    with FakeOscilloscope(state=ExperimentState(), seed=0) as scope:
        assert "Fake" in scope.identify()


def test_measure_returns_finite_values() -> None:
    state = ExperimentState()
    state.update(combo_index=1, set_speed_rpm=300, set_frequency_hz=20.0, set_amplitude_vpp=3.0)
    with FakeOscilloscope(state=state, seed=0) as scope:
        m = scope.measure()
        assert m.frequency_hz is not None and m.frequency_hz > 0
        assert m.vpp_v is not None and m.vpp_v > 0
        assert m.ch2_vrms_dc_v is not None
        assert m.ch3_vrms_dc_v is not None


def test_vpp_increases_with_rpm() -> None:
    state = ExperimentState()
    with FakeOscilloscope(state=state, seed=0, noise_amplitude=0.0) as scope:
        state.update(combo_index=1, set_speed_rpm=100, set_frequency_hz=20.0, set_amplitude_vpp=3.0)
        low = scope.measure().vpp_v
        state.update(combo_index=2, set_speed_rpm=900, set_frequency_hz=20.0, set_amplitude_vpp=3.0)
        high = scope.measure().vpp_v
    assert low is not None and high is not None
    assert high > low


def test_determinism() -> None:
    state = ExperimentState()
    state.update(combo_index=1, set_speed_rpm=200, set_frequency_hz=20.0, set_amplitude_vpp=3.0)
    a = FakeOscilloscope(state=state, seed=7)
    b = FakeOscilloscope(state=state, seed=7)
    with a, b:
        assert a.measure() == b.measure()
