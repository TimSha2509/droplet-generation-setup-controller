from droplet_lab.sweep import SweepCombination, expand_sweep


def test_expand_yields_full_cross_product_in_rpm_freq_amp_order() -> None:
    combos = expand_sweep(
        speeds_rpm=[200, 800],
        frequencies_hz=[20.0, 25.0],
        amplitudes_vpp=[3.0, 5.0],
        hold_s=30.0,
    )
    assert len(combos) == 8
    assert [c.set_speed_rpm for c in combos] == [200, 200, 200, 200, 800, 800, 800, 800]
    assert [c.frequency_hz for c in combos] == [20, 20, 25, 25, 20, 20, 25, 25]
    assert [c.amplitude_vpp for c in combos] == [3, 5, 3, 5, 3, 5, 3, 5]


def test_first_combo_changed_is_initial() -> None:
    combos = expand_sweep(speeds_rpm=[200], frequencies_hz=[20.0], amplitudes_vpp=[3.0], hold_s=1.0)
    assert combos[0].changed == "initial"
    assert combos[0].combo_index == 1


def test_changed_flag_tracks_outer_to_inner() -> None:
    combos = expand_sweep(
        speeds_rpm=[200, 800],
        frequencies_hz=[20.0, 25.0],
        amplitudes_vpp=[3.0, 5.0],
        hold_s=1.0,
    )
    assert [c.changed for c in combos] == [
        "initial", "amp", "freq", "amp", "rpm", "amp", "freq", "amp",
    ]


def test_combo_index_is_one_based_and_consecutive() -> None:
    combos = expand_sweep(speeds_rpm=[1], frequencies_hz=[1.0], amplitudes_vpp=[1.0, 2.0, 3.0], hold_s=1.0)
    assert [c.combo_index for c in combos] == [1, 2, 3]


def test_single_combination_is_initial() -> None:
    combos = expand_sweep(speeds_rpm=[200], frequencies_hz=[20.0], amplitudes_vpp=[3.0], hold_s=1.0)
    assert len(combos) == 1
    assert combos[0].changed == "initial"


def test_hold_s_propagated() -> None:
    combos = expand_sweep(speeds_rpm=[200], frequencies_hz=[20.0], amplitudes_vpp=[3.0], hold_s=42.0)
    assert combos[0].hold_s == 42.0


def test_duplicate_amplitude_still_classified_as_amp_step() -> None:
    combos = expand_sweep(
        speeds_rpm=[200], frequencies_hz=[20.0], amplitudes_vpp=[3.0, 3.0], hold_s=1.0
    )
    assert [c.changed for c in combos] == ["initial", "amp"]
