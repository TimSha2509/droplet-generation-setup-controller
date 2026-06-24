"""Cross-product expansion of the experiment sweep.

A sweep is RPM, frequency, and either function-generator amplitude or target
peak-to-peak displacement. ``expand_sweep`` produces the full cross-product with
RPM outermost and the actuation axis innermost. When requested, that full
cross-product is shuffled with a deterministic Fisher-Yates shuffle before
execution.

Each combination carries a ``changed`` flag that names the slowest parameter
that differs from the previous executed combination. The orchestrator uses that
to pick the right stabilization time.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal

ChangedKind = Literal["initial", "rpm", "freq", "amp"]
RANDOM_SHUFFLE_SEED = 0
RANDOMIZATION_ALGORITHM = "Fisher-Yates shuffle using Python random.Random(seed=0)"


@dataclass(frozen=True, slots=True)
class SweepCombination:
    combo_index: int
    set_speed_rpm: int
    frequency_hz: float
    amplitude_vpp: float
    hold_s: float
    changed: ChangedKind
    target_displacement_um: float | None = None


def expand_sweep(
    *,
    speeds_rpm: list[int],
    frequencies_hz: list[float],
    amplitudes_vpp: list[float] | None = None,
    displacements_um: list[float] | None = None,
    resolved_amplitudes_vpp: dict[tuple[float, float], float] | None = None,
    hold_s: float,
    randomize: bool = False,
) -> list[SweepCombination]:
    if (amplitudes_vpp is None) == (displacements_um is None):
        raise ValueError("exactly one of amplitudes_vpp or displacements_um is required")
    if displacements_um is not None and resolved_amplitudes_vpp is None:
        raise ValueError("resolved_amplitudes_vpp is required for displacement sweeps")

    out: list[SweepCombination] = []
    idx = 0
    for rpm in speeds_rpm:
        for freq in frequencies_hz:
            for amp, target_displacement_um in _actuation_points(
                freq,
                amplitudes_vpp=amplitudes_vpp,
                displacements_um=displacements_um,
                resolved_amplitudes_vpp=resolved_amplitudes_vpp,
            ):
                idx += 1
                out.append(
                    SweepCombination(
                        combo_index=idx,
                        set_speed_rpm=rpm,
                        frequency_hz=float(freq),
                        amplitude_vpp=float(amp),
                        target_displacement_um=target_displacement_um,
                        hold_s=hold_s,
                        changed="initial",
                    )
                )
    if randomize:
        _fisher_yates_shuffle(out, seed=RANDOM_SHUFFLE_SEED)
    return _with_execution_changes(out)


def _fisher_yates_shuffle(combos: list[SweepCombination], *, seed: int) -> None:
    rng = random.Random(seed)
    for i in range(len(combos) - 1, 0, -1):
        j = rng.randrange(i + 1)
        combos[i], combos[j] = combos[j], combos[i]


def _with_execution_changes(combos: list[SweepCombination]) -> list[SweepCombination]:
    out: list[SweepCombination] = []
    prev_rpm: int | None = None
    prev_freq: float | None = None
    for combo in combos:
        if prev_rpm is None:
            changed: ChangedKind = "initial"
        elif combo.set_speed_rpm != prev_rpm:
            changed = "rpm"
        elif combo.frequency_hz != prev_freq:
            changed = "freq"
        else:
            changed = "amp"
        out.append(
            SweepCombination(
                combo_index=combo.combo_index,
                set_speed_rpm=combo.set_speed_rpm,
                frequency_hz=combo.frequency_hz,
                amplitude_vpp=combo.amplitude_vpp,
                target_displacement_um=combo.target_displacement_um,
                hold_s=combo.hold_s,
                changed=changed,
            )
        )
        prev_rpm = combo.set_speed_rpm
        prev_freq = combo.frequency_hz
    return out


def _actuation_points(
    frequency_hz: float,
    *,
    amplitudes_vpp: list[float] | None,
    displacements_um: list[float] | None,
    resolved_amplitudes_vpp: dict[tuple[float, float], float] | None,
) -> list[tuple[float, float | None]]:
    if amplitudes_vpp is not None:
        return [(float(amp), None) for amp in amplitudes_vpp]
    assert displacements_um is not None
    assert resolved_amplitudes_vpp is not None
    return [
        (
            float(resolved_amplitudes_vpp[(float(frequency_hz), float(displacement_um))]),
            float(displacement_um),
        )
        for displacement_um in displacements_um
    ]
