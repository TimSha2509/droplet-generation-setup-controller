"""Cross-product expansion of the experiment sweep.

A sweep is three lists (RPM, frequency, amplitude). ``expand_sweep`` produces
a flat ordered list of ``SweepCombination`` instances iterating RPM outermost,
then frequency, then amplitude innermost. Each combination carries a
``changed`` flag that names the slowest parameter that differs from the
previous combination — used by the orchestrator to pick the right
stabilization time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ChangedKind = Literal["initial", "rpm", "freq", "amp"]


@dataclass(frozen=True, slots=True)
class SweepCombination:
    combo_index: int
    set_speed_rpm: int
    frequency_hz: float
    amplitude_vpp: float
    hold_s: float
    changed: ChangedKind


def expand_sweep(
    *,
    speeds_rpm: list[int],
    frequencies_hz: list[float],
    amplitudes_vpp: list[float],
    hold_s: float,
) -> list[SweepCombination]:
    out: list[SweepCombination] = []
    prev_rpm: int | None = None
    prev_freq: float | None = None
    idx = 0
    for rpm in speeds_rpm:
        for freq in frequencies_hz:
            for amp in amplitudes_vpp:
                idx += 1
                if prev_rpm is None:
                    changed: ChangedKind = "initial"
                elif rpm != prev_rpm:
                    changed = "rpm"
                elif freq != prev_freq:
                    changed = "freq"
                else:
                    changed = "amp"
                out.append(
                    SweepCombination(
                        combo_index=idx,
                        set_speed_rpm=rpm,
                        frequency_hz=float(freq),
                        amplitude_vpp=float(amp),
                        hold_s=hold_s,
                        changed=changed,
                    )
                )
                prev_rpm = rpm
                prev_freq = freq
    return out
