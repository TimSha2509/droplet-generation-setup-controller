# mypy: disable-error-code="comparison-overlap,unreachable"

import pytest

from droplet_lab.devices.pump_fake import FakePump


def test_fake_pump_satisfies_protocol() -> None:
    from droplet_lab.devices.base import Pump

    p: Pump = FakePump(seed=0)  # structural typing check
    assert p is not None


def test_initial_speed_zero() -> None:
    with FakePump(seed=0) as p:
        assert p.get_target_speed_rpm() == 0
        assert p.get_actual_speed_rpm() == 0


def test_set_speed_ramps_to_target() -> None:
    with FakePump(seed=0, acceleration_rpm_per_s=10000) as p:
        p.set_speed(200)
        # advance simulated time to settle
        p.advance(seconds=1.0)
        actual = p.get_actual_speed_rpm()
        assert actual is not None
        assert abs(actual - 200) <= 5


def test_stop_sets_target_to_zero() -> None:
    with FakePump(seed=0) as p:
        p.set_speed(300)
        p.stop()
        assert p.get_target_speed_rpm() == 0


def test_temperature_drifts_within_bounds() -> None:
    with FakePump(seed=0) as p:
        p.set_speed(500)
        for _ in range(20):
            p.advance(seconds=1.0)
        t = p.get_temperature_c()
        assert t is not None
        assert 15.0 < t < 80.0


def test_determinism_with_same_seed() -> None:
    p1 = FakePump(seed=42)
    p2 = FakePump(seed=42)
    p1.set_speed(300)
    p2.set_speed(300)
    for _ in range(10):
        p1.advance(0.5)
        p2.advance(0.5)
    assert p1.get_temperature_c() == p2.get_temperature_c()


def test_context_manager_open_close() -> None:
    p = FakePump(seed=0)
    assert not p.is_open
    with p:
        assert p.is_open
    assert not p.is_open


def test_set_speed_rejects_negative() -> None:
    with FakePump(seed=0) as p:
        with pytest.raises(ValueError):
            p.set_speed(-1)
