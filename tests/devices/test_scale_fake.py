from droplet_lab.devices.scale_fake import FakeScale


def test_satisfies_protocol() -> None:
    from droplet_lab.devices.base import Scale

    s: Scale = FakeScale()
    assert s is not None


def test_returns_increasing_weight() -> None:
    with FakeScale(rate_g_per_s=1.0) as scale:
        first = scale.read_weight_g()
        scale.advance(seconds=2.0)
        second = scale.read_weight_g()
    assert first is not None and second is not None
    assert second > first


def test_determinism() -> None:
    a = FakeScale(seed=3)
    b = FakeScale(seed=3)
    with a, b:
        a.advance(1.0)
        b.advance(1.0)
        assert a.read_weight_g() == b.read_weight_g()
