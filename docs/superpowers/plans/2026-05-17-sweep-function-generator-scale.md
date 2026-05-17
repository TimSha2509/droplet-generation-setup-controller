# Sweep + Function Generator + Scale Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the linear ramp with a full RPM × Frequency × Amplitude sweep, add the PSG9080 function generator as a new device, record an initial scale weight before pump start, and persist per-combo raw data (pump.csv, oscilloscope.csv) plus a `runs.csv` batch report.

**Architecture:** Big-bang YAML schema swap (`ramp` → `sweep`, `actuation` → `vibrometer`, new `devices.function_generator`). New `SweepCombination` model expands the cross-product into a flat ordered list (rpm outermost). `ExperimentState` gains `combo_index`/`set_frequency_hz`/`set_amplitude_vpp` so all worker streams tag samples with the full parameter set. Workers rotate their CSV writer per combo into the matching step-folder via a new `RotatingCsvWriter`. The function generator is driven directly by the orchestrator (no worker thread). Initial scale weight is read by the orchestrator before any worker starts.

**Tech Stack:** Python 3.12, pydantic v2 (`extra="forbid"`, `frozen=True`), typer, loguru, pyserial, pyvisa, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-05-17-sweep-function-generator-scale-design.md`

---

## File Map

**Create:**
- `src/droplet_lab/sweep.py` — `SweepCombination` dataclass + `expand_sweep()`
- `src/droplet_lab/devices/function_generator_psg9080.py`
- `src/droplet_lab/devices/function_generator_fake.py`
- `tests/unit/test_sweep.py`
- `tests/devices/test_function_generator_psg9080.py`
- `tests/devices/test_function_generator_fake.py`
- `experiments/example_sweep_mini.yaml` — used by integration test

**Modify:**
- `src/droplet_lab/config.py` — schema swap (see Task 1)
- `src/droplet_lab/state.py` — extend snapshot + `update()`
- `src/droplet_lab/storage.py` — new row dataclasses, `RotatingCsvWriter`, `combo_folder_name`, `create_combo_folder`, `append_runs_row`, drop global pump/scope CSV openers
- `src/droplet_lab/devices/base.py` — add `FunctionGenerator` Protocol
- `src/droplet_lab/devices/__init__.py` — factory + export
- `src/droplet_lab/devices/scale_sartorius.py` — 1200 baud, 7E1, xonxoff
- `src/droplet_lab/workers/pump_worker.py` — rotate CSV per combo
- `src/droplet_lab/workers/scope_worker.py` — rotate CSV per combo
- `src/droplet_lab/workers/scale_worker.py` — `phase="sweep"`, new row fields, configurable interval
- `src/droplet_lab/orchestrator.py` — new `_walk_sweep`, initial scale read, FG init, runs.csv append
- `src/droplet_lab/cli.py` — imports, simulate-only, new schema scaffolder
- `experiments/example_hpmc.yaml` — new schema
- `tests/unit/test_config.py`, `tests/unit/test_state.py`, `tests/unit/test_storage.py`
- `tests/devices/test_factory.py`, `tests/devices/test_scale_sartorius.py`
- `tests/workers/test_pump_worker.py`, `test_scope_worker.py`, `test_scale_worker.py`
- `tests/integration/test_orchestrator_end_to_end.py`
- `tests/cli/test_cli.py`

**Note on intermediate state:** Because the schema break is wholesale, `uv run pytest` will NOT pass between Task 1 and Task 8. After each task, only the **directly affected** test files are expected to pass; the rest will fail at import time (renamed symbols). The plan calls out which tests to run per task. Task 9 brings the suite green again.

---

## Task 1: Sweep config types + validation

**Files:**
- Create: `src/droplet_lab/sweep.py`
- Create: `tests/unit/test_sweep.py`
- Modify: `src/droplet_lab/config.py` (full rewrite of the schema block)
- Modify: `tests/unit/test_config.py`

### Step 1.1: Write `SweepCombination` + `expand_sweep` tests

- [ ] Create `tests/unit/test_sweep.py`:

```python
from droplet_lab.sweep import SweepCombination, expand_sweep


def test_expand_yields_full_cross_product_in_rpm_freq_amp_order() -> None:
    combos = expand_sweep(
        speeds_rpm=[200, 800],
        frequencies_hz=[20.0, 25.0],
        amplitudes_vpp=[3.0, 5.0],
        hold_s=30.0,
    )
    assert len(combos) == 8
    # rpm outermost: combos 1-4 are rpm=200, combos 5-8 are rpm=800
    assert [c.set_speed_rpm for c in combos] == [200, 200, 200, 200, 800, 800, 800, 800]
    # within each rpm: freq cycles slower than amp
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
    # 1:(200,20,3) initial, 2:(200,20,5) amp, 3:(200,25,3) freq, 4:(200,25,5) amp,
    # 5:(800,20,3) rpm,    6:(800,20,5) amp, 7:(800,25,3) freq, 8:(800,25,5) amp
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
```

- [ ] **Step 1.2: Run tests to verify they fail (module missing).**

Run: `uv run pytest tests/unit/test_sweep.py -v`
Expected: ImportError / "No module named droplet_lab.sweep".

- [ ] **Step 1.3: Implement `src/droplet_lab/sweep.py`:**

```python
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
```

- [ ] **Step 1.4: Run tests to verify they pass.**

Run: `uv run pytest tests/unit/test_sweep.py -v`
Expected: 6 passed.

- [ ] **Step 1.5: Rewrite `src/droplet_lab/config.py`.**

Replace the whole file with:

```python
"""Pydantic v2 models for experiment configuration.

A complete experiment is one YAML file under ``experiments/``. ``load_experiment``
parses, validates, and returns an ``ExperimentConfig``. Any structural problem in
the YAML (typo, wrong type, missing field, value out of range) raises
``ValidationError`` with a precise location.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Final, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    PositiveFloat,
    PositiveInt,
    field_validator,
    model_validator,
)

MAX_AMPLITUDE_VPP: Final[float] = 9.5


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VibrometerConfig(_StrictModel):
    factor_um_per_v: PositiveFloat


class SweepConfig(_StrictModel):
    speeds_rpm: Annotated[list[PositiveInt], Field(min_length=1)]
    frequencies_hz: Annotated[list[PositiveFloat], Field(min_length=1)]
    amplitudes_vpp: Annotated[list[PositiveFloat], Field(min_length=1)]
    hold_s: PositiveFloat

    @field_validator("amplitudes_vpp")
    @classmethod
    def _amplitudes_within_hardware_limit(cls, value: list[float]) -> list[float]:
        for amp in value:
            if amp > MAX_AMPLITUDE_VPP:
                raise ValueError(
                    f"amplitude {amp} Vpp exceeds hardware limit {MAX_AMPLITUDE_VPP} Vpp"
                )
        return value


class TimingConfig(_StrictModel):
    stabilization_rpm_change_s: NonNegativeFloat
    stabilization_freq_change_s: NonNegativeFloat
    stabilization_amp_change_s: NonNegativeFloat
    image_interval_s: PositiveFloat
    camera_latency_tolerance_s: NonNegativeFloat = 0.0


class LimitsConfig(_StrictModel):
    max_speed_rpm: PositiveInt = 1000


class PumpConfig(_StrictModel):
    port: str
    baudrate: PositiveInt = 9600


class OscilloscopeConfig(_StrictModel):
    visa_resource: str
    timeout_ms: PositiveInt = 5000


class CameraConfig(_StrictModel):
    digicam_url: str = "http://localhost:5513"
    request_timeout_s: PositiveFloat = 10.0


class FunctionGeneratorConfig(_StrictModel):
    port: str
    channel: Literal[1, 2] = 1
    baudrate: PositiveInt = 115200


class ScaleConfig(_StrictModel):
    enabled: bool = False
    port: str | None = None
    baudrate: PositiveInt = 1200
    interval_s: PositiveFloat = 5.0


class DevicesConfig(_StrictModel):
    pump: PumpConfig
    oscilloscope: OscilloscopeConfig
    camera: CameraConfig
    function_generator: FunctionGeneratorConfig
    scale: ScaleConfig = Field(default_factory=ScaleConfig)


class OutputConfig(_StrictModel):
    base_dir: Path

    @field_validator("base_dir", mode="after")
    @classmethod
    def _resolve(cls, value: Path) -> Path:
        return value.expanduser().resolve()


class ExperimentConfig(_StrictModel):
    experiment_id: str = Field(min_length=1)
    nozzle_id: str = Field(min_length=1)
    vibrometer: VibrometerConfig
    sweep: SweepConfig
    timing: TimingConfig
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    devices: DevicesConfig
    output: OutputConfig

    @model_validator(mode="after")
    def _speeds_within_limits(self) -> ExperimentConfig:
        max_rpm = self.limits.max_speed_rpm
        for i, rpm in enumerate(self.sweep.speeds_rpm):
            if rpm > max_rpm:
                raise ValueError(
                    f"sweep.speeds_rpm[{i}]={rpm} exceeds limits.max_speed_rpm={max_rpm}"
                )
        return self

    @model_validator(mode="after")
    def _hold_s_covers_worst_case_stabilization(self) -> ExperimentConfig:
        if self.sweep.hold_s < self.timing.stabilization_rpm_change_s:
            raise ValueError(
                f"sweep.hold_s={self.sweep.hold_s} must be >= "
                f"timing.stabilization_rpm_change_s={self.timing.stabilization_rpm_change_s}"
            )
        return self


def load_experiment(path: Path | str) -> ExperimentConfig:
    """Load and validate an experiment YAML file."""
    raw = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping at the YAML root")
    return ExperimentConfig.model_validate(data)
```

- [ ] **Step 1.6: Rewrite `tests/unit/test_config.py`.**

Replace the file with:

```python
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from droplet_lab.config import (
    MAX_AMPLITUDE_VPP,
    CameraConfig,
    DevicesConfig,
    ExperimentConfig,
    FunctionGeneratorConfig,
    OscilloscopeConfig,
    OutputConfig,
    PumpConfig,
    ScaleConfig,
    SweepConfig,
    VibrometerConfig,
    load_experiment,
)


def _minimal_dict(tmp_path: Path) -> dict[str, object]:
    return {
        "experiment_id": "TEST_01",
        "nozzle_id": "1mm_A",
        "vibrometer": {"factor_um_per_v": 5280},
        "sweep": {
            "speeds_rpm": [200, 250],
            "frequencies_hz": [20.0, 25.0],
            "amplitudes_vpp": [3.0, 5.0],
            "hold_s": 1.0,
        },
        "timing": {
            "stabilization_rpm_change_s": 0.5,
            "stabilization_freq_change_s": 0.2,
            "stabilization_amp_change_s": 0.1,
            "image_interval_s": 0.5,
            "camera_latency_tolerance_s": 0.5,
        },
        "limits": {"max_speed_rpm": 1000},
        "devices": {
            "pump": {"port": "COM3", "baudrate": 9600},
            "oscilloscope": {"visa_resource": "USB0::INSTR"},
            "camera": {"digicam_url": "http://localhost:5513"},
            "function_generator": {"port": "COM4", "channel": 1, "baudrate": 115200},
            "scale": {"enabled": False},
        },
        "output": {"base_dir": str(tmp_path)},
    }


def test_minimal_config_validates(tmp_path: Path) -> None:
    cfg = ExperimentConfig.model_validate(_minimal_dict(tmp_path))
    assert cfg.experiment_id == "TEST_01"
    assert cfg.vibrometer.factor_um_per_v == 5280
    assert cfg.sweep.speeds_rpm == [200, 250]
    assert cfg.devices.function_generator.channel == 1
    assert cfg.devices.scale.enabled is False


def test_amplitude_above_hardware_limit_rejected(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    data["sweep"]["amplitudes_vpp"] = [3.0, 10.0]  # > 9.5
    with pytest.raises(ValidationError) as exc:
        ExperimentConfig.model_validate(data)
    assert "hardware limit" in str(exc.value)


def test_max_amplitude_constant() -> None:
    assert MAX_AMPLITUDE_VPP == 9.5


def test_empty_speeds_rejected(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    data["sweep"]["speeds_rpm"] = []
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(data)


def test_empty_frequencies_rejected(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    data["sweep"]["frequencies_hz"] = []
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(data)


def test_empty_amplitudes_rejected(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    data["sweep"]["amplitudes_vpp"] = []
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(data)


def test_speed_above_limit_rejected(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    data["sweep"]["speeds_rpm"] = [1500]
    with pytest.raises(ValidationError) as exc:
        ExperimentConfig.model_validate(data)
    assert "max_speed_rpm" in str(exc.value)


def test_hold_s_must_cover_rpm_stabilization(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    data["sweep"]["hold_s"] = 0.2
    data["timing"]["stabilization_rpm_change_s"] = 0.5
    with pytest.raises(ValidationError) as exc:
        ExperimentConfig.model_validate(data)
    assert "stabilization_rpm_change_s" in str(exc.value)


def test_function_generator_channel_must_be_1_or_2(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    data["devices"]["function_generator"]["channel"] = 3
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(data)


def test_unknown_field_rejected(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    data["unknown_field"] = "oops"
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(data)


def test_load_experiment_from_yaml(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    yaml_path = tmp_path / "exp.yaml"
    yaml_path.write_text(yaml.safe_dump(data))
    cfg = load_experiment(yaml_path)
    assert cfg.experiment_id == "TEST_01"


def test_pump_config_defaults() -> None:
    cfg = PumpConfig(port="COM3")
    assert cfg.baudrate == 9600


def test_function_generator_defaults() -> None:
    cfg = FunctionGeneratorConfig(port="COM4")
    assert cfg.channel == 1
    assert cfg.baudrate == 115200


def test_scale_defaults() -> None:
    cfg = ScaleConfig()
    assert cfg.enabled is False
    assert cfg.port is None
    assert cfg.baudrate == 1200
    assert cfg.interval_s == 5.0


def test_devices_config_partial() -> None:
    devices = DevicesConfig(
        pump=PumpConfig(port="COM3"),
        oscilloscope=OscilloscopeConfig(visa_resource="USB0::INSTR"),
        camera=CameraConfig(digicam_url="http://localhost:5513"),
        function_generator=FunctionGeneratorConfig(port="COM4"),
        scale=ScaleConfig(),
    )
    assert devices.scale.enabled is False
    assert devices.function_generator.channel == 1


def test_example_yaml_validates() -> None:
    """The shipped example YAML must always validate."""
    cfg = load_experiment(Path("experiments/example_hpmc.yaml"))
    assert cfg.experiment_id


def test_output_config_resolves_path(tmp_path: Path) -> None:
    cfg = OutputConfig(base_dir=tmp_path)
    assert cfg.base_dir.is_absolute()


def test_vibrometer_factor_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        VibrometerConfig(factor_um_per_v=0)


def test_sweep_config_standalone() -> None:
    s = SweepConfig(
        speeds_rpm=[200], frequencies_hz=[20.0], amplitudes_vpp=[3.0], hold_s=1.0
    )
    assert s.speeds_rpm == [200]
```

Note: `test_example_yaml_validates` will FAIL until Task 9 rewrites `experiments/example_hpmc.yaml`. Expect it to fail at this point; we'll fix it then.

- [ ] **Step 1.7: Run config tests (most pass, one xfailed).**

Run: `uv run pytest tests/unit/test_config.py tests/unit/test_sweep.py -v`
Expected: all pass except `test_example_yaml_validates` (fails — old YAML still on disk). That's the only acceptable failure.

- [ ] **Step 1.8: Commit.**

```bash
git add src/droplet_lab/sweep.py src/droplet_lab/config.py \
        tests/unit/test_sweep.py tests/unit/test_config.py
git -c commit.gpgsign=false commit -m "Replace ramp/actuation with sweep schema and add function_generator config"
```

---

## Task 2: Extend `ExperimentState` with combo / freq / amp

**Files:**
- Modify: `src/droplet_lab/state.py`
- Modify: `tests/unit/test_state.py`

### Step 2.1: Update tests

- [ ] Rewrite `tests/unit/test_state.py`:

```python
# mypy: disable-error-code="comparison-overlap"
import threading

from droplet_lab.state import (
    CameraStatus,
    ExperimentState,
    ExperimentStatus,
    StepStatus,
)


def test_status_enums_have_string_values() -> None:
    assert ExperimentStatus.RUNNING == "running"
    assert ExperimentStatus.COMPLETED == "completed"
    assert ExperimentStatus.ABORTED == "aborted"
    assert ExperimentStatus.FAILED == "failed"

    assert StepStatus.PLANNED == "planned"
    assert StepStatus.STABILIZING == "stabilizing"
    assert StepStatus.IMAGING == "imaging"
    assert StepStatus.COMPLETED == "completed"
    assert StepStatus.COMPLETED_NO_IMAGING == "completed_no_imaging"
    assert StepStatus.CAMERA_TIMEOUT == "camera_timeout"
    assert StepStatus.CAMERA_FAILED == "camera_failed"
    assert StepStatus.ABORTED == "aborted"

    assert CameraStatus.NOT_STARTED == "not_started"
    assert CameraStatus.STARTING == "starting"
    assert CameraStatus.RUNNING == "running"
    assert CameraStatus.COMPLETED == "completed"
    assert CameraStatus.FAILED == "failed"
    assert CameraStatus.ABORTED == "aborted"


def test_experiment_state_initial_values() -> None:
    state = ExperimentState()
    assert state.combo_index is None
    assert state.set_speed_rpm is None
    assert state.set_frequency_hz is None
    assert state.set_amplitude_vpp is None


def test_experiment_state_update_round_trips_all_fields() -> None:
    state = ExperimentState()
    state.update(combo_index=7, set_speed_rpm=800, set_frequency_hz=25.0, set_amplitude_vpp=5.0)
    snap = state.snapshot()
    assert snap.combo_index == 7
    assert snap.set_speed_rpm == 800
    assert snap.set_frequency_hz == 25.0
    assert snap.set_amplitude_vpp == 5.0


def test_experiment_state_update_is_thread_safe() -> None:
    state = ExperimentState()

    def writer(start: int) -> None:
        for i in range(start, start + 100):
            state.update(
                combo_index=i,
                set_speed_rpm=i * 10,
                set_frequency_hz=float(i),
                set_amplitude_vpp=float(i) / 2.0,
            )

    threads = [threading.Thread(target=writer, args=(i * 1000,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    snap = state.snapshot()
    assert snap.combo_index is not None
    assert snap.set_speed_rpm == snap.combo_index * 10
    assert snap.set_frequency_hz == float(snap.combo_index)
```

- [ ] **Step 2.2: Run; expect failure (signature mismatch).**

Run: `uv run pytest tests/unit/test_state.py -v`
Expected: failures — `combo_index` attribute missing, `update()` doesn't accept new kwargs.

- [ ] **Step 2.3: Update `src/droplet_lab/state.py`.**

Replace the lower half of the file (from `@dataclass...ExperimentStateSnapshot` to end) with:

```python
@dataclass(frozen=True, slots=True)
class ExperimentStateSnapshot:
    """Immutable point-in-time view of ExperimentState (safe to share across threads)."""

    combo_index: int | None = None
    set_speed_rpm: int | None = None
    set_frequency_hz: float | None = None
    set_amplitude_vpp: float | None = None


class ExperimentState:
    """Thread-safe holder for the currently active sweep combination.

    Workers read this every measurement to tag rows with the correct combo
    (index, rpm, freq, amp). The orchestrator updates it on every combination
    transition.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot = ExperimentStateSnapshot()

    @property
    def combo_index(self) -> int | None:
        with self._lock:
            return self._snapshot.combo_index

    @property
    def set_speed_rpm(self) -> int | None:
        with self._lock:
            return self._snapshot.set_speed_rpm

    @property
    def set_frequency_hz(self) -> float | None:
        with self._lock:
            return self._snapshot.set_frequency_hz

    @property
    def set_amplitude_vpp(self) -> float | None:
        with self._lock:
            return self._snapshot.set_amplitude_vpp

    def update(
        self,
        *,
        combo_index: int,
        set_speed_rpm: int,
        set_frequency_hz: float,
        set_amplitude_vpp: float,
    ) -> None:
        with self._lock:
            self._snapshot = replace(
                self._snapshot,
                combo_index=combo_index,
                set_speed_rpm=set_speed_rpm,
                set_frequency_hz=set_frequency_hz,
                set_amplitude_vpp=set_amplitude_vpp,
            )

    def snapshot(self) -> ExperimentStateSnapshot:
        with self._lock:
            return self._snapshot
```

- [ ] **Step 2.4: Run state tests.**

Run: `uv run pytest tests/unit/test_state.py -v`
Expected: all pass.

- [ ] **Step 2.5: Commit.**

```bash
git add src/droplet_lab/state.py tests/unit/test_state.py
git -c commit.gpgsign=false commit -m "Extend ExperimentState with combo_index, frequency, amplitude"
```

---

## Task 3: Storage — Row schemas, RotatingCsvWriter, combo folders, runs.csv

**Files:**
- Modify: `src/droplet_lab/storage.py`
- Modify: `tests/unit/test_storage.py`

### Step 3.1: Update row dataclasses + helpers in storage.py

- [ ] Replace `src/droplet_lab/storage.py` with:

```python
"""Output directory layout and CSV writers.

Every experiment writes into one timestamped folder under ``base_dir``::

    <base_dir>/<UTC-timestamp>__<experiment_id>/
        experiment.json
        experiment.log
        scale.csv          (only if scale enabled — includes phase=initial row)
        runs.csv           (one row per completed combination)
        steps/
            combo_001_rpm0200_f20Hz_amp3V/
                step.json
                pump.csv
                oscilloscope.csv
                images/

CSVs use ``;`` separators (DE-Excel friendly) and UTF-8.
All timestamps are UTC ISO 8601 with microsecond precision and a trailing ``Z``.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

from droplet_lab.sweep import SweepCombination

_INVALID_FILENAME_CHARS = '<>:"/\\|?*'


def sanitize_filename(text: str) -> str:
    out = text
    for ch in _INVALID_FILENAME_CHARS:
        out = out.replace(ch, "_")
    return out.strip().replace(" ", "_")


def utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def utc_now_filename_safe() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")


def combo_folder_name(
    combo_index: int, set_speed_rpm: int, frequency_hz: float, amplitude_vpp: float
) -> str:
    """Stable, sortable name for one combination's step folder.

    Format: ``combo_<NNN>_rpm<RRRR>_f<FREQ>Hz_amp<AMP>V``.
    """
    return (
        f"combo_{combo_index:03d}_rpm{set_speed_rpm:04d}"
        f"_f{frequency_hz:g}Hz_amp{amplitude_vpp:g}V"
    )


# -------- Row dataclasses --------


@dataclass(frozen=True, slots=True)
class PumpRow:
    timestamp_utc: str
    elapsed_s: float
    combo_index: int | None
    set_speed_rpm: int | None
    set_frequency_hz: float | None
    set_amplitude_vpp: float | None
    actual_speed_rpm: int | None
    temperature_c: float | None


@dataclass(frozen=True, slots=True)
class OscilloscopeRow:
    timestamp_utc: str
    elapsed_s: float
    combo_index: int | None
    set_speed_rpm: int | None
    set_frequency_hz: float | None
    set_amplitude_vpp: float | None
    frequency_hz: float | None
    vpp_v: float | None
    p2p_displacement_um: float | None
    ch2_vrms_dc_v: float | None
    ch3_vrms_dc_v: float | None


@dataclass(frozen=True, slots=True)
class ScaleRow:
    timestamp_utc: str
    elapsed_s: float
    phase: str
    combo_index: int | None
    set_speed_rpm: int | None
    set_frequency_hz: float | None
    set_amplitude_vpp: float | None
    weight_g: float | None


@dataclass(frozen=True, slots=True)
class RunsRow:
    timestamp_utc: str
    combo_index: int
    experiment_id: str
    nozzle_id: str
    set_speed_rpm: int
    set_frequency_hz: float
    set_amplitude_vpp: float
    hold_s: float
    step_folder: str
    status: str
    n_captures: int
    failure_reason: str | None


# -------- CSV writer wrappers --------


def _fieldnames_for(row_cls: type) -> list[str]:
    return [f.name for f in row_cls.__dataclass_fields__.values()]


class CsvRowWriter:
    """Writes dataclass rows to a CSV file (semicolon-separated, UTF-8)."""

    def __init__(self, fp: IO[str], fieldnames: list[str]) -> None:
        self._fp = fp
        self._writer = csv.DictWriter(fp, fieldnames=fieldnames, delimiter=";")
        self._writer.writeheader()
        fp.flush()

    def write(self, row: Any) -> None:
        data = asdict(row)
        sanitized = {k: ("" if v is None else v) for k, v in data.items()}
        self._writer.writerow(sanitized)
        self._fp.flush()


class RotatingCsvWriter:
    """A semicolon-separated CSV writer that can be re-opened in a new folder.

    Used by Pump/Scope workers: on every combination transition, the worker
    calls ``close()`` then ``open_in(new_step_folder, filename)`` to start a
    fresh per-combo file.
    """

    def __init__(self, row_cls: type) -> None:
        self._fieldnames = _fieldnames_for(row_cls)
        self._fp: IO[str] | None = None
        self._writer: CsvRowWriter | None = None

    def open_in(self, folder: Path, filename: str) -> None:
        if self._fp is not None:
            self.close()
        path = folder / filename
        self._fp = path.open("w", encoding="utf-8", newline="")
        self._writer = CsvRowWriter(self._fp, self._fieldnames)

    def write(self, row: Any) -> None:
        if self._writer is None:
            raise RuntimeError("RotatingCsvWriter.write before open_in")
        self._writer.write(row)

    def close(self) -> None:
        if self._fp is not None:
            self._fp.close()
        self._fp = None
        self._writer = None

    @property
    def is_open(self) -> bool:
        return self._fp is not None


# -------- Experiment directory --------


@dataclass(frozen=True, slots=True)
class ExperimentDirectory:
    """Filesystem layout for one experiment run."""

    root: Path

    @property
    def steps_dir(self) -> Path:
        return self.root / "steps"

    @property
    def runs_csv_path(self) -> Path:
        return self.root / "runs.csv"

    @classmethod
    def create(cls, *, base_dir: Path, experiment_id: str) -> ExperimentDirectory:
        base_dir.mkdir(parents=True, exist_ok=True)
        folder = base_dir / f"{utc_now_filename_safe()}__{sanitize_filename(experiment_id)}"
        folder.mkdir()
        (folder / "steps").mkdir()
        return cls(root=folder)

    def create_combo_folder(self, combo: SweepCombination) -> Path:
        folder = self.steps_dir / combo_folder_name(
            combo.combo_index,
            combo.set_speed_rpm,
            combo.frequency_hz,
            combo.amplitude_vpp,
        )
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "images").mkdir(exist_ok=True)
        return folder

    def append_scale_row(self, row: ScaleRow) -> None:
        """Append one row to scale.csv (creates the file + header on first call)."""
        path = self.root / "scale.csv"
        fieldnames = _fieldnames_for(ScaleRow)
        is_new = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=fieldnames, delimiter=";")
            if is_new:
                writer.writeheader()
            data = asdict(row)
            sanitized = {k: ("" if v is None else v) for k, v in data.items()}
            writer.writerow(sanitized)

    def append_runs_row(self, row: RunsRow) -> None:
        path = self.runs_csv_path
        fieldnames = _fieldnames_for(RunsRow)
        is_new = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=fieldnames, delimiter=";")
            if is_new:
                writer.writeheader()
            data = asdict(row)
            sanitized = {k: ("" if v is None else v) for k, v in data.items()}
            writer.writerow(sanitized)

    @staticmethod
    def write_json(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
```

### Step 3.2: Rewrite `tests/unit/test_storage.py`

- [ ] Read the existing file first:

Run: `cat tests/unit/test_storage.py`

(You can keep tests that exercise `sanitize_filename`, `utc_now_iso`, `utc_now_filename_safe`, `ExperimentDirectory.create`, `write_json` unchanged. Replace tests that depended on `open_pump_csv`/`open_oscilloscope_csv`/`create_step_folder`/`PumpRow.step_index` with the ones below.)

Add/replace with:

```python
from pathlib import Path

import pytest

from droplet_lab.storage import (
    ExperimentDirectory,
    OscilloscopeRow,
    PumpRow,
    RotatingCsvWriter,
    RunsRow,
    ScaleRow,
    combo_folder_name,
    sanitize_filename,
    utc_now_iso,
)
from droplet_lab.sweep import SweepCombination


def _combo(idx: int = 1, rpm: int = 200, freq: float = 20.0, amp: float = 3.0):
    return SweepCombination(
        combo_index=idx,
        set_speed_rpm=rpm,
        frequency_hz=freq,
        amplitude_vpp=amp,
        hold_s=1.0,
        changed="initial" if idx == 1 else "amp",
    )


def test_combo_folder_name_format() -> None:
    assert combo_folder_name(1, 200, 20.0, 3.0) == "combo_001_rpm0200_f20Hz_amp3V"
    assert combo_folder_name(42, 1000, 25.5, 9.5) == "combo_042_rpm1000_f25.5Hz_amp9.5V"


def test_create_combo_folder_creates_subdirs(tmp_path: Path) -> None:
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    folder = exp.create_combo_folder(_combo(1))
    assert folder.is_dir()
    assert (folder / "images").is_dir()
    assert folder.name == "combo_001_rpm0200_f20Hz_amp3V"


def test_rotating_csv_writer_writes_header_and_rotates(tmp_path: Path) -> None:
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    folder_a = exp.create_combo_folder(_combo(1))
    folder_b = exp.create_combo_folder(_combo(2, amp=5.0))

    writer = RotatingCsvWriter(PumpRow)
    writer.open_in(folder_a, "pump.csv")
    writer.write(PumpRow(utc_now_iso(), 0.0, 1, 200, 20.0, 3.0, 200, 25.0))
    writer.open_in(folder_b, "pump.csv")  # implicit close of A
    writer.write(PumpRow(utc_now_iso(), 1.0, 2, 200, 20.0, 5.0, 201, 25.1))
    writer.close()

    text_a = (folder_a / "pump.csv").read_text()
    text_b = (folder_b / "pump.csv").read_text()
    assert "combo_index" in text_a.splitlines()[0]
    assert text_a.count("\n") == 2  # header + 1 row
    assert text_b.count("\n") == 2


def test_rotating_csv_writer_write_before_open_raises(tmp_path: Path) -> None:
    writer = RotatingCsvWriter(PumpRow)
    with pytest.raises(RuntimeError):
        writer.write(PumpRow(utc_now_iso(), 0.0, 1, 200, 20.0, 3.0, 200, 25.0))


def test_append_scale_row_writes_header_once_and_phase_column(tmp_path: Path) -> None:
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    exp.append_scale_row(ScaleRow(utc_now_iso(), 0.0, "initial", None, None, None, None, 12.345))
    exp.append_scale_row(ScaleRow(utc_now_iso(), 1.0, "sweep", 1, 200, 20.0, 3.0, 12.500))
    text = (exp.root / "scale.csv").read_text()
    lines = text.splitlines()
    assert "phase" in lines[0]
    assert "initial" in lines[1]
    assert "sweep" in lines[2]
    assert len(lines) == 3


def test_append_runs_row_writes_header_once(tmp_path: Path) -> None:
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    row = RunsRow(
        timestamp_utc=utc_now_iso(),
        combo_index=1,
        experiment_id="X",
        nozzle_id="n",
        set_speed_rpm=200,
        set_frequency_hz=20.0,
        set_amplitude_vpp=3.0,
        hold_s=1.0,
        step_folder="steps/combo_001_rpm0200_f20Hz_amp3V",
        status="completed",
        n_captures=5,
        failure_reason=None,
    )
    exp.append_runs_row(row)
    exp.append_runs_row(row)  # second append should NOT rewrite header
    text = exp.runs_csv_path.read_text()
    lines = text.splitlines()
    assert lines[0].startswith("timestamp_utc;")
    assert len(lines) == 3  # header + 2 rows


def test_oscilloscope_row_has_new_columns() -> None:
    row = OscilloscopeRow(
        timestamp_utc=utc_now_iso(),
        elapsed_s=0.0,
        combo_index=1,
        set_speed_rpm=200,
        set_frequency_hz=20.0,
        set_amplitude_vpp=3.0,
        frequency_hz=20.0,
        vpp_v=3.1,
        p2p_displacement_um=16368.0,
        ch2_vrms_dc_v=None,
        ch3_vrms_dc_v=None,
    )
    assert row.set_frequency_hz == 20.0


def test_sanitize_filename_strips_unsafe_chars() -> None:
    assert sanitize_filename("a/b\\c:d*e") == "a_b_c_d_e"
```

- [ ] **Step 3.3: Run storage tests.**

Run: `uv run pytest tests/unit/test_storage.py -v`
Expected: all new tests pass. (Old tests that depended on removed APIs were intentionally dropped.)

- [ ] **Step 3.4: Commit.**

```bash
git add src/droplet_lab/storage.py tests/unit/test_storage.py
git -c commit.gpgsign=false commit -m "Add RotatingCsvWriter, combo folders, runs.csv, new row fields"
```

---

## Task 4: Function Generator — Protocol + Fake + PSG9080 + Factory

**Files:**
- Modify: `src/droplet_lab/devices/base.py` (add Protocol)
- Create: `src/droplet_lab/devices/function_generator_fake.py`
- Create: `src/droplet_lab/devices/function_generator_psg9080.py`
- Modify: `src/droplet_lab/devices/__init__.py` (factory + export)
- Create: `tests/devices/test_function_generator_fake.py`
- Create: `tests/devices/test_function_generator_psg9080.py`
- Modify: `tests/devices/test_factory.py`

### Step 4.1: Add `FunctionGenerator` Protocol

- [ ] Edit `src/droplet_lab/devices/base.py` — append at the end:

```python
class FunctionGenerator(Protocol, AbstractContextManager["FunctionGenerator"]):
    def set_sine(self) -> None: ...
    def set_frequency_hz(self, hz: float) -> None: ...
    def set_amplitude_vpp(self, vpp: float) -> None: ...
    def enable_output(self, on: bool) -> None: ...
```

### Step 4.2: Write the Fake first (used by tests + simulate mode)

- [ ] Create `tests/devices/test_function_generator_fake.py`:

```python
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


def test_amplitude_above_limit_raises() -> None:
    fg = FakeFunctionGenerator()
    with fg:
        with pytest.raises(ValueError, match="exceeds hardware limit"):
            fg.set_amplitude_vpp(9.6)
```

- [ ] Run the failing test:

Run: `uv run pytest tests/devices/test_function_generator_fake.py -v`
Expected: ImportError.

- [ ] Create `src/droplet_lab/devices/function_generator_fake.py`:

```python
"""In-memory function generator simulator."""

from __future__ import annotations

from types import TracebackType
from typing import Any

from loguru import logger

from droplet_lab.config import MAX_AMPLITUDE_VPP


class FakeFunctionGenerator:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.is_sine: bool = False
        self.frequency_hz: float | None = None
        self.amplitude_vpp: float | None = None
        self.output_on: bool = False
        self._open = False
        self._log = logger.bind(component="fg")

    def __enter__(self) -> FakeFunctionGenerator:
        self._open = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.output_on = False
        self._open = False

    def set_sine(self) -> None:
        self.calls.append(("set_sine",))
        self.is_sine = True
        self._log.debug("fake fg: set_sine")

    def set_frequency_hz(self, hz: float) -> None:
        self.calls.append(("set_frequency_hz", float(hz)))
        self.frequency_hz = float(hz)
        self._log.debug("fake fg: frequency={} Hz", hz)

    def set_amplitude_vpp(self, vpp: float) -> None:
        if vpp > MAX_AMPLITUDE_VPP:
            raise ValueError(
                f"amplitude {vpp} Vpp exceeds hardware limit {MAX_AMPLITUDE_VPP} Vpp"
            )
        self.calls.append(("set_amplitude_vpp", float(vpp)))
        self.amplitude_vpp = float(vpp)
        self._log.debug("fake fg: amplitude={} Vpp", vpp)

    def enable_output(self, on: bool) -> None:
        self.calls.append(("enable_output", bool(on)))
        self.output_on = bool(on)
        self._log.debug("fake fg: output={}", on)
```

- [ ] Run:

Run: `uv run pytest tests/devices/test_function_generator_fake.py -v`
Expected: 3 pass.

### Step 4.3: Write PSG9080 tests (mock serial)

- [ ] Create `tests/devices/test_function_generator_psg9080.py`:

```python
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
    # set_sine then enable_output(False)
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
    assert b":w10=0,0.\r\n" in sent  # output off
    fake.close.assert_called_once()


def test_max_amplitude_constant_reexported() -> None:
    assert MAX_AMPLITUDE_VPP == 9.5
```

- [ ] Run:

Run: `uv run pytest tests/devices/test_function_generator_psg9080.py -v`
Expected: ImportError.

- [ ] Create `src/droplet_lab/devices/function_generator_psg9080.py`:

```python
"""PSG9080 function generator driver (serial, ASCII command protocol).

Commands (channel 1 / channel 2):
    :w11=0.        / :w12=0.            — set sine wave
    :w13=<n>,0.    / :w14=<n>,0.        — frequency, n = Hz × 1000
    :w15=<n>.      / :w16=<n>.          — amplitude, n = Vpp × 1000
    :w10=<a>,<b>.                       — output enable (a=Ch1, b=Ch2 in {0,1})
"""

from __future__ import annotations

import time
from types import TracebackType
from typing import Final

import serial
from loguru import logger

from droplet_lab.config import MAX_AMPLITUDE_VPP

__all__ = ["PSG9080Generator", "MAX_AMPLITUDE_VPP"]

_RESPONSE_READ_DELAY_S: Final[float] = 0.05
_OPEN_SETTLE_S: Final[float] = 0.2


class PSG9080Generator:
    def __init__(
        self,
        *,
        port: str,
        channel: int,
        baudrate: int = 115200,
        timeout_s: float = 1.0,
    ) -> None:
        if channel not in (1, 2):
            raise ValueError(f"channel must be 1 or 2, got {channel}")
        self._port = port
        self._channel = channel
        self._baudrate = baudrate
        self._timeout_s = timeout_s
        self._ser: serial.Serial | None = None
        self._log = logger.bind(component="fg")

    def __enter__(self) -> PSG9080Generator:
        self._ser = serial.Serial(
            port=self._port,
            baudrate=self._baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self._timeout_s,
        )
        time.sleep(_OPEN_SETTLE_S)
        self._log.info("opened PSG9080 on {} (channel {})", self._port, self._channel)
        # safe defaults: sine, output off
        self.set_sine()
        self.enable_output(False)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._ser is not None and self._ser.is_open:
            try:
                self.enable_output(False)
            finally:
                self._ser.close()
        self._ser = None

    def set_sine(self) -> None:
        cmd = ":w11=0." if self._channel == 1 else ":w12=0."
        self._send(cmd)

    def set_frequency_hz(self, hz: float) -> None:
        scaled = int(round(hz * 1000))
        cmd = (
            f":w13={scaled},0."
            if self._channel == 1
            else f":w14={scaled},0."
        )
        self._send(cmd)

    def set_amplitude_vpp(self, vpp: float) -> None:
        if vpp > MAX_AMPLITUDE_VPP:
            raise ValueError(
                f"amplitude {vpp} Vpp exceeds hardware limit {MAX_AMPLITUDE_VPP} Vpp"
            )
        scaled = int(round(vpp * 1000))
        cmd = (
            f":w15={scaled}."
            if self._channel == 1
            else f":w16={scaled}."
        )
        self._send(cmd)

    def enable_output(self, on: bool) -> None:
        if self._channel == 1:
            cmd = f":w10={1 if on else 0},0."
        else:
            cmd = f":w10=0,{1 if on else 0}."
        self._send(cmd)

    def _send(self, command: str) -> None:
        if self._ser is None:
            raise RuntimeError("PSG9080 is not open")
        full = (command + "\r\n").encode("ascii")
        self._ser.write(full)
        time.sleep(_RESPONSE_READ_DELAY_S)
        response = self._ser.read_all().decode("ascii", errors="ignore").strip()
        if response:
            self._log.debug("fg sent={!r} resp={!r}", command, response)
        else:
            self._log.debug("fg sent={!r}", command)
```

- [ ] Run:

Run: `uv run pytest tests/devices/test_function_generator_psg9080.py -v`
Expected: 9 pass.

### Step 4.4: Factory + exports

- [ ] Replace `src/droplet_lab/devices/__init__.py` with:

```python
"""Hardware device abstractions and factories."""

from droplet_lab.config import (
    CameraConfig,
    FunctionGeneratorConfig,
    OscilloscopeConfig,
    PumpConfig,
    ScaleConfig,
)
from droplet_lab.devices.base import (
    Camera,
    FunctionGenerator,
    Oscilloscope,
    Pump,
    Scale,
    ScopeMeasurement,
)
from droplet_lab.devices.camera_digicam import DigiCamCamera
from droplet_lab.devices.camera_fake import FakeCamera
from droplet_lab.devices.function_generator_fake import FakeFunctionGenerator
from droplet_lab.devices.function_generator_psg9080 import PSG9080Generator
from droplet_lab.devices.oscilloscope_fake import FakeOscilloscope
from droplet_lab.devices.oscilloscope_keysight import KeysightOscilloscope
from droplet_lab.devices.pump_fake import FakePump
from droplet_lab.devices.pump_mzr7245 import MZR7245Pump
from droplet_lab.devices.scale_fake import FakeScale
from droplet_lab.devices.scale_sartorius import SartoriusScale
from droplet_lab.state import ExperimentState

__all__ = [
    "Camera",
    "FunctionGenerator",
    "Oscilloscope",
    "Pump",
    "Scale",
    "ScopeMeasurement",
    "build_camera",
    "build_function_generator",
    "build_oscilloscope",
    "build_pump",
    "build_scale",
]


def build_pump(cfg: PumpConfig, *, simulate: bool) -> Pump:
    if simulate:
        return FakePump()
    return MZR7245Pump(port=cfg.port, baudrate=cfg.baudrate)


def build_oscilloscope(
    cfg: OscilloscopeConfig,
    *,
    state: ExperimentState,
    simulate: bool,
) -> Oscilloscope:
    if simulate:
        return FakeOscilloscope(state=state)
    return KeysightOscilloscope(visa_resource=cfg.visa_resource, timeout_ms=cfg.timeout_ms)


def build_camera(cfg: CameraConfig, *, simulate: bool) -> Camera:
    if simulate:
        return FakeCamera()
    return DigiCamCamera(url=cfg.digicam_url, request_timeout_s=cfg.request_timeout_s)


def build_function_generator(
    cfg: FunctionGeneratorConfig, *, simulate: bool
) -> FunctionGenerator:
    if simulate:
        return FakeFunctionGenerator()
    return PSG9080Generator(port=cfg.port, channel=cfg.channel, baudrate=cfg.baudrate)


def build_scale(cfg: ScaleConfig, *, simulate: bool) -> Scale:
    if simulate:
        return FakeScale()
    if cfg.port is None:
        raise ValueError("ScaleConfig.port must be set when simulate=False")
    return SartoriusScale(port=cfg.port, baudrate=cfg.baudrate)
```

- [ ] Read existing `tests/devices/test_factory.py` and extend with the new function-generator factory tests:

Run: `cat tests/devices/test_factory.py`

(Read it to understand its style, then) append at the end:

```python
from droplet_lab.config import FunctionGeneratorConfig
from droplet_lab.devices import (
    FakeFunctionGenerator,
    PSG9080Generator,
    build_function_generator,
)


def test_build_function_generator_returns_fake_when_simulating() -> None:
    fg = build_function_generator(FunctionGeneratorConfig(port="COM4"), simulate=True)
    assert isinstance(fg, FakeFunctionGenerator)


def test_build_function_generator_returns_real_when_not_simulating() -> None:
    # Don't actually open the port; just check the class.
    fg = build_function_generator(
        FunctionGeneratorConfig(port="COMX", channel=2), simulate=False
    )
    assert isinstance(fg, PSG9080Generator)
```

- [ ] Run:

Run: `uv run pytest tests/devices/test_factory.py tests/devices/test_function_generator_fake.py tests/devices/test_function_generator_psg9080.py -v`
Expected: all pass.

- [ ] **Step 4.5: Commit.**

```bash
git add src/droplet_lab/devices/ tests/devices/test_function_generator_fake.py \
        tests/devices/test_function_generator_psg9080.py tests/devices/test_factory.py
git -c commit.gpgsign=false commit -m "Add PSG9080 function generator device with fake and factory"
```

---

## Task 5: Sartorius scale — switch to 1200 baud / 7E1 / XON-XOFF

**Files:**
- Modify: `src/droplet_lab/devices/scale_sartorius.py`
- Modify: `tests/devices/test_scale_sartorius.py`

The new `Script_read_Scale_v2.py` uses `baudrate=1200, bytesize=SEVENBITS, parity=EVEN, stopbits=ONE, xonxoff=True`. The existing driver already does 7E1 but at 9600. We switch the default to 1200 and add `xonxoff=True`. ConfigDefault is already 1200 from Task 1.

### Step 5.1: Update tests

- [ ] Read `tests/devices/test_scale_sartorius.py`. Locate the test that mocks `serial.Serial` and asserts the kwargs it was called with. Update the assertion to:

```python
serial.Serial.assert_called_once_with(
    port="COM3",
    baudrate=1200,
    bytesize=serial.SEVENBITS,
    parity=serial.PARITY_EVEN,
    stopbits=serial.STOPBITS_ONE,
    timeout=1.0,
    xonxoff=True,
)
```

If no such assertion exists yet, add a new test:

```python
from unittest.mock import MagicMock, patch

import serial

from droplet_lab.devices.scale_sartorius import SartoriusScale


def test_enter_opens_serial_with_7e1_at_1200_baud_xonxoff() -> None:
    fake = MagicMock()
    fake.readline.return_value = b"+ 12.345 g\r\n"
    with patch("droplet_lab.devices.scale_sartorius.serial.Serial", return_value=fake) as ctor:
        with SartoriusScale(port="COM3"):
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
```

### Step 5.2: Update the driver

- [ ] Modify `src/droplet_lab/devices/scale_sartorius.py` — change the default baudrate and add xonxoff in `__enter__`:

In `__init__`, change `baudrate: int = 9600` to `baudrate: int = 1200`.

In `__enter__`, change the `serial.Serial(...)` call to include `xonxoff=True`:

```python
self._ser = serial.Serial(
    port=self._port,
    baudrate=self._baudrate,
    bytesize=serial.SEVENBITS,
    parity=serial.PARITY_EVEN,
    stopbits=serial.STOPBITS_ONE,
    timeout=self._timeout_s,
    xonxoff=True,
)
```

- [ ] Run:

Run: `uv run pytest tests/devices/test_scale_sartorius.py -v`
Expected: all pass (including the new wiring test).

- [ ] **Step 5.3: Commit.**

```bash
git add src/droplet_lab/devices/scale_sartorius.py tests/devices/test_scale_sartorius.py
git -c commit.gpgsign=false commit -m "Switch Sartorius scale to 1200 baud 7E1 with XON/XOFF"
```

---

## Task 6: Workers — rotate CSV per combo, new tag fields, configurable scale interval

**Files:**
- Modify: `src/droplet_lab/workers/pump_worker.py`
- Modify: `src/droplet_lab/workers/scope_worker.py`
- Modify: `src/droplet_lab/workers/scale_worker.py`
- Modify: `tests/workers/test_pump_worker.py`
- Modify: `tests/workers/test_scope_worker.py`
- Modify: `tests/workers/test_scale_worker.py`

### Step 6.1: PumpWorker — rotate per combo

- [ ] Replace `src/droplet_lab/workers/pump_worker.py`:

```python
"""Pump worker thread.

Continuously logs pump telemetry to the current combo's ``pump.csv`` and
consumes ``SetSpeedCommand`` messages from the orchestrator's queue. Rotates
the output file whenever ``ExperimentState.combo_index`` advances. Stops
cleanly on ``stop_event``; signals ``error_event`` on hardware failure.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from droplet_lab.devices.base import Pump
from droplet_lab.state import ExperimentState
from droplet_lab.storage import (
    ExperimentDirectory,
    PumpRow,
    RotatingCsvWriter,
    combo_folder_name,
    utc_now_iso,
)


@dataclass(frozen=True, slots=True)
class SetSpeedCommand:
    rpm: int


class PumpWorker:
    def __init__(
        self,
        *,
        pump: Pump,
        state: ExperimentState,
        command_queue: queue.Queue[SetSpeedCommand],
        stop_event: threading.Event,
        error_event: threading.Event,
        log_interval_s: float,
        experiment_dir: ExperimentDirectory,
    ) -> None:
        self._pump = pump
        self._state = state
        self._queue = command_queue
        self._stop = stop_event
        self._error = error_event
        self._log_interval_s = log_interval_s
        self._exp = experiment_dir
        self._log = logger.bind(component="pump")

    def run(self) -> None:
        start = time.monotonic()
        next_log = start
        writer = RotatingCsvWriter(PumpRow)
        current_combo: int | None = None
        try:
            while not self._stop.is_set():
                try:
                    cmd = self._queue.get_nowait()
                except queue.Empty:
                    cmd = None
                if cmd is not None:
                    self._pump.set_speed(cmd.rpm)
                    self._log.info("set speed -> {} rpm", cmd.rpm)

                now = time.monotonic()
                if now >= next_log:
                    snap = self._state.snapshot()
                    if snap.combo_index is not None and snap.combo_index != current_combo:
                        current_combo = snap.combo_index
                        folder = self._combo_folder(snap)
                        writer.open_in(folder, "pump.csv")
                    if writer.is_open:
                        writer.write(
                            PumpRow(
                                timestamp_utc=utc_now_iso(),
                                elapsed_s=round(now - start, 3),
                                combo_index=snap.combo_index,
                                set_speed_rpm=snap.set_speed_rpm,
                                set_frequency_hz=snap.set_frequency_hz,
                                set_amplitude_vpp=snap.set_amplitude_vpp,
                                actual_speed_rpm=self._pump.get_actual_speed_rpm(),
                                temperature_c=self._pump.get_temperature_c(),
                            )
                        )
                    next_log = now + self._log_interval_s
                time.sleep(0.02)
        except Exception:
            self._log.exception("pump worker crashed")
            self._error.set()
        finally:
            writer.close()
            try:
                self._pump.stop()
            except Exception:
                self._log.exception("failed to stop pump on shutdown")
            self._log.info("pump worker finished")

    def _combo_folder(self, snap) -> Path:
        assert snap.combo_index is not None
        assert snap.set_speed_rpm is not None
        assert snap.set_frequency_hz is not None
        assert snap.set_amplitude_vpp is not None
        return self._exp.steps_dir / combo_folder_name(
            snap.combo_index, snap.set_speed_rpm, snap.set_frequency_hz, snap.set_amplitude_vpp
        )
```

Note: the worker DOES NOT call `create_combo_folder` — the orchestrator already created it. The worker only opens its CSV inside an existing folder. That keeps the responsibility clear.

### Step 6.2: ScopeWorker — same pattern

- [ ] Replace `src/droplet_lab/workers/scope_worker.py`:

```python
"""Oscilloscope worker thread."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from loguru import logger

from droplet_lab.devices.base import Oscilloscope
from droplet_lab.state import ExperimentState
from droplet_lab.storage import (
    ExperimentDirectory,
    OscilloscopeRow,
    RotatingCsvWriter,
    combo_folder_name,
    utc_now_iso,
)


class ScopeWorker:
    def __init__(
        self,
        *,
        scope: Oscilloscope,
        state: ExperimentState,
        stop_event: threading.Event,
        error_event: threading.Event,
        log_interval_s: float,
        vibrometer_factor_um_per_v: float,
        experiment_dir: ExperimentDirectory,
    ) -> None:
        self._scope = scope
        self._state = state
        self._stop = stop_event
        self._error = error_event
        self._interval = log_interval_s
        self._factor = vibrometer_factor_um_per_v
        self._exp = experiment_dir
        self._log = logger.bind(component="scope")

    def run(self) -> None:
        start = time.monotonic()
        next_log = start
        writer = RotatingCsvWriter(OscilloscopeRow)
        current_combo: int | None = None
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                if now >= next_log:
                    snap = self._state.snapshot()
                    if snap.combo_index is not None and snap.combo_index != current_combo:
                        current_combo = snap.combo_index
                        folder = self._combo_folder(snap)
                        writer.open_in(folder, "oscilloscope.csv")
                    if writer.is_open:
                        m = self._scope.measure()
                        p2p = m.vpp_v * self._factor if m.vpp_v is not None else None
                        writer.write(
                            OscilloscopeRow(
                                timestamp_utc=utc_now_iso(),
                                elapsed_s=round(now - start, 3),
                                combo_index=snap.combo_index,
                                set_speed_rpm=snap.set_speed_rpm,
                                set_frequency_hz=snap.set_frequency_hz,
                                set_amplitude_vpp=snap.set_amplitude_vpp,
                                frequency_hz=m.frequency_hz,
                                vpp_v=m.vpp_v,
                                p2p_displacement_um=p2p,
                                ch2_vrms_dc_v=m.ch2_vrms_dc_v,
                                ch3_vrms_dc_v=m.ch3_vrms_dc_v,
                            )
                        )
                    next_log = now + self._interval
                time.sleep(0.02)
        except Exception:
            self._log.exception("scope worker crashed")
            self._error.set()
        finally:
            writer.close()
            self._log.info("scope worker finished")

    def _combo_folder(self, snap) -> Path:
        assert snap.combo_index is not None
        assert snap.set_speed_rpm is not None
        assert snap.set_frequency_hz is not None
        assert snap.set_amplitude_vpp is not None
        return self._exp.steps_dir / combo_folder_name(
            snap.combo_index, snap.set_speed_rpm, snap.set_frequency_hz, snap.set_amplitude_vpp
        )
```

### Step 6.3: ScaleWorker — phase + new fields, append per row

- [ ] Replace `src/droplet_lab/workers/scale_worker.py`:

```python
"""Scale worker thread (optional — only spawned if the scale is enabled).

Appends to the global ``scale.csv`` at the configured interval. The
orchestrator writes the very first ``phase=initial`` row (also via
``append_scale_row``) before this worker is started; all rows from this worker
have ``phase=sweep``.
"""

from __future__ import annotations

import threading
import time

from loguru import logger

from droplet_lab.devices.base import Scale
from droplet_lab.state import ExperimentState
from droplet_lab.storage import ExperimentDirectory, ScaleRow, utc_now_iso


class ScaleWorker:
    def __init__(
        self,
        *,
        scale: Scale,
        state: ExperimentState,
        stop_event: threading.Event,
        error_event: threading.Event,
        log_interval_s: float,
        experiment_dir: ExperimentDirectory,
    ) -> None:
        self._scale = scale
        self._state = state
        self._stop = stop_event
        self._error = error_event
        self._interval = log_interval_s
        self._exp = experiment_dir
        self._log = logger.bind(component="scale")

    def run(self) -> None:
        start = time.monotonic()
        next_log = start
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                if now >= next_log:
                    snap = self._state.snapshot()
                    self._exp.append_scale_row(
                        ScaleRow(
                            timestamp_utc=utc_now_iso(),
                            elapsed_s=round(now - start, 3),
                            phase="sweep",
                            combo_index=snap.combo_index,
                            set_speed_rpm=snap.set_speed_rpm,
                            set_frequency_hz=snap.set_frequency_hz,
                            set_amplitude_vpp=snap.set_amplitude_vpp,
                            weight_g=self._scale.read_weight_g(),
                        )
                    )
                    next_log = now + self._interval
                time.sleep(0.02)
        except Exception:
            self._log.exception("scale worker crashed")
            self._error.set()
        finally:
            self._log.info("scale worker finished")
```

`append_scale_row` was already added to `ExperimentDirectory` in Task 3 — both the orchestrator (initial row) and this worker (sweep rows) call into it, and the file is opened in append mode each time so there's no race.

### Step 6.4: Update worker tests

- [ ] Rewrite `tests/workers/test_pump_worker.py`:

```python
import queue
import threading
import time

from droplet_lab.devices.pump_fake import FakePump
from droplet_lab.state import ExperimentState
from droplet_lab.storage import ExperimentDirectory, combo_folder_name
from droplet_lab.workers.pump_worker import PumpWorker, SetSpeedCommand


def _make_combo_folder(exp: ExperimentDirectory, idx: int, rpm: int, freq: float, amp: float):
    folder = exp.steps_dir / combo_folder_name(idx, rpm, freq, amp)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "images").mkdir(exist_ok=True)
    return folder


def test_writes_pump_csv_into_combo_folder(tmp_path) -> None:
    state = ExperimentState()
    state.update(combo_index=1, set_speed_rpm=200, set_frequency_hz=20.0, set_amplitude_vpp=3.0)
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    _make_combo_folder(exp, 1, 200, 20.0, 3.0)

    cmd_q: queue.Queue[SetSpeedCommand] = queue.Queue()
    stop = threading.Event()
    error = threading.Event()
    pump = FakePump()
    with pump:
        worker = PumpWorker(
            pump=pump, state=state, command_queue=cmd_q,
            stop_event=stop, error_event=error,
            log_interval_s=0.05, experiment_dir=exp,
        )
        t = threading.Thread(target=worker.run)
        t.start()
        time.sleep(0.3)
        stop.set()
        t.join(timeout=2.0)
    assert not error.is_set()
    combo_folder = exp.steps_dir / combo_folder_name(1, 200, 20.0, 3.0)
    text = (combo_folder / "pump.csv").read_text()
    assert "set_frequency_hz" in text.splitlines()[0]
    assert text.count("\n") >= 2  # header + at least 1 row


def test_rotates_csv_when_combo_changes(tmp_path) -> None:
    state = ExperimentState()
    state.update(combo_index=1, set_speed_rpm=200, set_frequency_hz=20.0, set_amplitude_vpp=3.0)
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    _make_combo_folder(exp, 1, 200, 20.0, 3.0)
    _make_combo_folder(exp, 2, 200, 20.0, 5.0)

    cmd_q: queue.Queue[SetSpeedCommand] = queue.Queue()
    stop = threading.Event()
    error = threading.Event()
    pump = FakePump()
    with pump:
        worker = PumpWorker(
            pump=pump, state=state, command_queue=cmd_q,
            stop_event=stop, error_event=error,
            log_interval_s=0.04, experiment_dir=exp,
        )
        t = threading.Thread(target=worker.run)
        t.start()
        time.sleep(0.2)
        state.update(combo_index=2, set_speed_rpm=200, set_frequency_hz=20.0, set_amplitude_vpp=5.0)
        time.sleep(0.2)
        stop.set()
        t.join(timeout=2.0)
    assert not error.is_set()
    combo_a = exp.steps_dir / combo_folder_name(1, 200, 20.0, 3.0) / "pump.csv"
    combo_b = exp.steps_dir / combo_folder_name(2, 200, 20.0, 5.0) / "pump.csv"
    assert combo_a.exists()
    assert combo_b.exists()
    # Each file has its own header
    assert combo_a.read_text().splitlines()[0].startswith("timestamp_utc;")
    assert combo_b.read_text().splitlines()[0].startswith("timestamp_utc;")


def test_consumes_set_speed_command(tmp_path) -> None:
    state = ExperimentState()
    state.update(combo_index=1, set_speed_rpm=0, set_frequency_hz=20.0, set_amplitude_vpp=3.0)
    pump = FakePump(acceleration_rpm_per_s=10000)
    with pump:
        exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
        _make_combo_folder(exp, 1, 0, 20.0, 3.0)
        cmd_q: queue.Queue[SetSpeedCommand] = queue.Queue()
        stop = threading.Event()
        error = threading.Event()
        worker = PumpWorker(
            pump=pump, state=state, command_queue=cmd_q,
            stop_event=stop, error_event=error,
            log_interval_s=0.05, experiment_dir=exp,
        )
        t = threading.Thread(target=worker.run)
        t.start()
        cmd_q.put(SetSpeedCommand(rpm=350))
        time.sleep(0.3)
        target_before_stop = pump.get_target_speed_rpm()
        stop.set()
        t.join(timeout=2.0)
    assert target_before_stop == 350
    assert pump.get_target_speed_rpm() == 0


def test_sets_error_event_on_pump_failure(tmp_path) -> None:
    class BoomPump(FakePump):
        def get_actual_speed_rpm(self):
            raise RuntimeError("device disconnected")

    pump = BoomPump()
    state = ExperimentState()
    state.update(combo_index=1, set_speed_rpm=0, set_frequency_hz=20.0, set_amplitude_vpp=3.0)
    with pump:
        exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
        from droplet_lab.storage import combo_folder_name as cfn
        folder = exp.steps_dir / cfn(1, 0, 20.0, 3.0)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "images").mkdir(exist_ok=True)
        cmd_q: queue.Queue[SetSpeedCommand] = queue.Queue()
        stop = threading.Event()
        error = threading.Event()
        worker = PumpWorker(
            pump=pump, state=state, command_queue=cmd_q,
            stop_event=stop, error_event=error,
            log_interval_s=0.05, experiment_dir=exp,
        )
        t = threading.Thread(target=worker.run)
        t.start()
        time.sleep(0.3)
        stop.set()
        t.join(timeout=2.0)
    assert error.is_set()
```

- [ ] Rewrite `tests/workers/test_scope_worker.py` — read the existing file, then mirror the structure of the pump tests above. Reuse `_make_combo_folder` (extract it to a small helper module or copy locally). Tests to write:
  1. `test_writes_oscilloscope_csv_into_combo_folder` — start worker with `combo_index=1`, sleep briefly, stop, assert `combo_001_*/oscilloscope.csv` contains a header with `set_frequency_hz` and at least one data row.
  2. `test_rotates_csv_when_combo_changes` — same shape as the pump test.
  3. `test_sets_error_event_on_scope_failure` — wrap `FakeOscilloscope` so `measure()` raises, then assert `error.is_set()`.

- [ ] Rewrite `tests/workers/test_scale_worker.py`:

```python
import threading
import time
from pathlib import Path

from droplet_lab.devices.scale_fake import FakeScale
from droplet_lab.state import ExperimentState
from droplet_lab.storage import ExperimentDirectory
from droplet_lab.workers.scale_worker import ScaleWorker


def test_scale_worker_writes_sweep_rows_with_full_combo_tags(tmp_path: Path) -> None:
    state = ExperimentState()
    state.update(combo_index=1, set_speed_rpm=200, set_frequency_hz=20.0, set_amplitude_vpp=3.0)
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    scale = FakeScale()
    stop = threading.Event()
    error = threading.Event()
    with scale:
        worker = ScaleWorker(
            scale=scale, state=state,
            stop_event=stop, error_event=error,
            log_interval_s=0.05, experiment_dir=exp,
        )
        t = threading.Thread(target=worker.run)
        t.start()
        time.sleep(0.25)
        stop.set()
        t.join(timeout=2.0)
    assert not error.is_set()
    lines = (exp.root / "scale.csv").read_text().splitlines()
    assert lines[0].split(";") == [
        "timestamp_utc", "elapsed_s", "phase",
        "combo_index", "set_speed_rpm",
        "set_frequency_hz", "set_amplitude_vpp",
        "weight_g",
    ]
    # All worker rows are phase=sweep with the tagged combo values.
    for line in lines[1:]:
        cols = line.split(";")
        assert cols[2] == "sweep"
        assert cols[3] == "1"
        assert cols[4] == "200"
        assert cols[5] == "20.0"
        assert cols[6] == "3.0"


def test_scale_worker_respects_log_interval(tmp_path: Path) -> None:
    state = ExperimentState()
    state.update(combo_index=1, set_speed_rpm=200, set_frequency_hz=20.0, set_amplitude_vpp=3.0)
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    scale = FakeScale()
    stop = threading.Event()
    error = threading.Event()
    with scale:
        worker = ScaleWorker(
            scale=scale, state=state,
            stop_event=stop, error_event=error,
            log_interval_s=0.2, experiment_dir=exp,
        )
        t = threading.Thread(target=worker.run)
        t.start()
        time.sleep(0.5)
        stop.set()
        t.join(timeout=2.0)
    n_data = len((exp.root / "scale.csv").read_text().splitlines()) - 1
    # ~2-3 samples in 0.5s with interval 0.2s
    assert 1 <= n_data <= 4
```

Run: `uv run pytest tests/workers/ -v`
Expected: all pass.

- [ ] **Step 6.5: Commit.**

```bash
git add src/droplet_lab/workers/ src/droplet_lab/storage.py tests/workers/
git -c commit.gpgsign=false commit -m "Rotate worker CSVs per combo, tag rows with frequency/amplitude, scale phase"
```

---

## Task 7: Orchestrator — sweep walk, FG, initial weight, runs.csv

**Files:**
- Modify: `src/droplet_lab/orchestrator.py`
- Update: `tests/integration/test_orchestrator_end_to_end.py` (full rewrite in Task 9)

### Step 7.1: Replace `src/droplet_lab/orchestrator.py`

- [ ] Use this implementation:

```python
"""Experiment orchestrator.

Owns the lifecycle of one experiment run:

* Build the ``ExperimentDirectory``, persist ``experiment.json``.
* Read an initial scale weight (if enabled) before any worker starts.
* Spawn ``PumpWorker`` / ``ScopeWorker`` (and optional ``ScaleWorker``).
* Walk the sweep cross-product (rpm × freq × amp), driving the function
  generator directly, signalling speed changes via the pump command queue,
  running camera capture, and appending one ``runs.csv`` row per combo.
* Watch for ``error_event`` / ``stop_event`` and shut down deterministically.
"""

from __future__ import annotations

import queue
import signal
import threading
import time
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from loguru import logger

from droplet_lab.config import ExperimentConfig
from droplet_lab.devices.base import (
    Camera,
    FunctionGenerator,
    Oscilloscope,
    Pump,
    Scale,
)
from droplet_lab.logging_setup import setup_logging
from droplet_lab.state import (
    CameraStatus,
    ExperimentState,
    ExperimentStatus,
    StepStatus,
)
from droplet_lab.storage import (
    ExperimentDirectory,
    RunsRow,
    ScaleRow,
    utc_now_iso,
)
from droplet_lab.sweep import SweepCombination, expand_sweep
from droplet_lab.workers.camera_worker import (
    CameraResult,
    CameraResultStatus,
    run_camera_capture,
)
from droplet_lab.workers.pump_worker import PumpWorker, SetSpeedCommand
from droplet_lab.workers.scale_worker import ScaleWorker
from droplet_lab.workers.scope_worker import ScopeWorker


class DeviceBundle(TypedDict):
    pump: Pump
    scope: Oscilloscope
    camera: Camera
    function_generator: FunctionGenerator
    scale: Scale


@dataclass(frozen=True, slots=True)
class OrchestratorResult:
    status: ExperimentStatus
    experiment_dir: ExperimentDirectory
    failure_reason: str | None = None


_PUMP_LOG_INTERVAL_S = 5.0
_SCOPE_LOG_INTERVAL_S = 15.0


class Orchestrator:
    def __init__(
        self,
        *,
        config: ExperimentConfig,
        devices: DeviceBundle,
        state: ExperimentState,
        install_signal_handler: bool = False,
    ) -> None:
        self._cfg = config
        self._devices = devices
        self._state = state
        self._stop = threading.Event()
        self._error = threading.Event()
        self._install_signal_handler = install_signal_handler
        self._log = logger.bind(component="orchestrator")
        self._initial_weight_g: float | None = None

    def request_stop(self) -> None:
        self._stop.set()

    def run(self) -> OrchestratorResult:
        exp = ExperimentDirectory.create(
            base_dir=self._cfg.output.base_dir,
            experiment_id=self._cfg.experiment_id,
        )
        setup_logging(exp.root)
        self._log.info("experiment dir: {}", exp.root)
        self._write_experiment_json(exp, status=ExperimentStatus.RUNNING)

        if self._install_signal_handler:
            signal.signal(signal.SIGINT, lambda *_: self._stop.set())

        result_status = ExperimentStatus.RUNNING
        failure_reason: str | None = None
        cmd_q: queue.Queue[SetSpeedCommand] = queue.Queue()

        try:
            with ExitStack() as stack:
                pump = stack.enter_context(self._devices["pump"])
                scope = stack.enter_context(self._devices["scope"])
                fg = stack.enter_context(self._devices["function_generator"])
                stack.enter_context(self._devices["camera"])
                scale_cm = (
                    stack.enter_context(self._devices["scale"])
                    if self._cfg.devices.scale.enabled
                    else None
                )

                # 1. Initial scale read BEFORE pump runs.
                if scale_cm is not None:
                    self._initial_weight_g = scale_cm.read_weight_g()
                    exp.append_scale_row(
                        ScaleRow(
                            timestamp_utc=utc_now_iso(),
                            elapsed_s=0.0,
                            phase="initial",
                            combo_index=None,
                            set_speed_rpm=None,
                            set_frequency_hz=None,
                            set_amplitude_vpp=None,
                            weight_g=self._initial_weight_g,
                        )
                    )
                    self._write_experiment_json(exp, status=ExperimentStatus.RUNNING)
                    self._log.info("initial weight: {} g", self._initial_weight_g)

                # 2. Function generator safe defaults.
                fg.set_sine()
                fg.enable_output(False)

                # 3. Expand sweep and pre-create the first folder so workers
                #    can open their CSVs immediately.
                combos = expand_sweep(
                    speeds_rpm=list(self._cfg.sweep.speeds_rpm),
                    frequencies_hz=list(self._cfg.sweep.frequencies_hz),
                    amplitudes_vpp=list(self._cfg.sweep.amplitudes_vpp),
                    hold_s=self._cfg.sweep.hold_s,
                )
                first = combos[0]
                self._state.update(
                    combo_index=first.combo_index,
                    set_speed_rpm=first.set_speed_rpm,
                    set_frequency_hz=first.frequency_hz,
                    set_amplitude_vpp=first.amplitude_vpp,
                )
                first_folder = exp.create_combo_folder(first)

                # 4. Start workers.
                pump_worker = PumpWorker(
                    pump=pump,
                    state=self._state,
                    command_queue=cmd_q,
                    stop_event=self._stop,
                    error_event=self._error,
                    log_interval_s=_PUMP_LOG_INTERVAL_S,
                    experiment_dir=exp,
                )
                scope_worker = ScopeWorker(
                    scope=scope,
                    state=self._state,
                    stop_event=self._stop,
                    error_event=self._error,
                    log_interval_s=_SCOPE_LOG_INTERVAL_S,
                    vibrometer_factor_um_per_v=self._cfg.vibrometer.factor_um_per_v,
                    experiment_dir=exp,
                )
                pump_thread = threading.Thread(target=pump_worker.run, name="pump")
                scope_thread = threading.Thread(target=scope_worker.run, name="scope")
                pump_thread.start()
                scope_thread.start()

                scale_thread: threading.Thread | None = None
                if scale_cm is not None:
                    scale_worker = ScaleWorker(
                        scale=scale_cm,
                        state=self._state,
                        stop_event=self._stop,
                        error_event=self._error,
                        log_interval_s=self._cfg.devices.scale.interval_s,
                        experiment_dir=exp,
                    )
                    scale_thread = threading.Thread(target=scale_worker.run, name="scale")
                    scale_thread.start()

                # 5. Walk the sweep.
                result_status, failure_reason = self._walk_sweep(
                    exp=exp,
                    combos=combos,
                    first_folder=first_folder,
                    cmd_q=cmd_q,
                    camera=self._devices["camera"],
                    fg=fg,
                )

                self._stop.set()
                pump_thread.join(timeout=10.0)
                scope_thread.join(timeout=10.0)
                if scale_thread is not None:
                    scale_thread.join(timeout=10.0)

                if self._error.is_set() and result_status is ExperimentStatus.COMPLETED:
                    result_status = ExperimentStatus.FAILED
                    failure_reason = failure_reason or "worker thread reported error"

        except Exception as e:
            self._log.exception("orchestrator crashed")
            result_status = ExperimentStatus.FAILED
            failure_reason = str(e)

        self._write_experiment_json(exp, status=result_status, failure_reason=failure_reason)
        return OrchestratorResult(
            status=result_status,
            experiment_dir=exp,
            failure_reason=failure_reason,
        )

    def _walk_sweep(
        self,
        *,
        exp: ExperimentDirectory,
        combos: list[SweepCombination],
        first_folder: Path,
        cmd_q: queue.Queue[SetSpeedCommand],
        camera: Camera,
        fg: FunctionGenerator,
    ) -> tuple[ExperimentStatus, str | None]:
        for combo in combos:
            if self._stop.is_set() or self._error.is_set():
                return self._final_status_after_break(), None

            # State update for combos 2..N (combo 1 was set before workers started).
            if combo.combo_index > 1:
                self._state.update(
                    combo_index=combo.combo_index,
                    set_speed_rpm=combo.set_speed_rpm,
                    set_frequency_hz=combo.frequency_hz,
                    set_amplitude_vpp=combo.amplitude_vpp,
                )

            # Pump speed: send on first combo and on every RPM change.
            if combo.changed in ("initial", "rpm"):
                cmd_q.put(SetSpeedCommand(rpm=combo.set_speed_rpm))

            # Function generator: frequency on every freq change, amplitude every combo.
            if combo.changed in ("initial", "rpm", "freq"):
                fg.set_frequency_hz(combo.frequency_hz)
            fg.set_amplitude_vpp(combo.amplitude_vpp)
            if combo.combo_index == 1:
                fg.enable_output(True)

            step_folder = first_folder if combo.combo_index == 1 \
                else exp.create_combo_folder(combo)
            step_meta = self._initial_step_meta(combo, step_folder)
            self._write_step_json(step_folder, step_meta)

            stabilization = self._stabilization_for(combo.changed)
            self._log.info(
                "combo {} rpm={} freq={}Hz amp={}Vpp changed={} — stabilizing {}s",
                combo.combo_index, combo.set_speed_rpm, combo.frequency_hz,
                combo.amplitude_vpp, combo.changed, stabilization,
            )
            step_meta["status"] = StepStatus.STABILIZING.value
            self._write_step_json(step_folder, step_meta)

            if self._wait(stabilization):
                step_meta["status"] = StepStatus.ABORTED.value
                step_meta["end_time_utc"] = utc_now_iso()
                self._write_step_json(step_folder, step_meta)
                self._append_runs_row(exp, combo, step_folder, step_meta, "aborted", None)
                return self._final_status_after_break(), None

            imaging_duration = max(0.0, combo.hold_s - stabilization)
            step_meta["status"] = StepStatus.IMAGING.value
            step_meta["imaging_planned_s"] = imaging_duration
            self._write_step_json(step_folder, step_meta)

            result: CameraResult = run_camera_capture(
                camera=camera,
                output_folder=step_folder / "images",
                interval_s=self._cfg.timing.image_interval_s,
                duration_s=imaging_duration,
                latency_tolerance_s=self._cfg.timing.camera_latency_tolerance_s,
                stop_event=self._stop,
            )
            step_meta["captures"] = result.captures
            step_meta["end_time_utc"] = utc_now_iso()

            match result.status:
                case CameraResultStatus.COMPLETED:
                    step_meta["status"] = StepStatus.COMPLETED.value
                    step_meta["camera_status"] = CameraStatus.COMPLETED.value
                    self._write_step_json(step_folder, step_meta)
                    self._append_runs_row(exp, combo, step_folder, step_meta, "completed", None)
                case CameraResultStatus.NO_IMAGING:
                    step_meta["status"] = StepStatus.COMPLETED_NO_IMAGING.value
                    step_meta["camera_status"] = CameraStatus.NOT_STARTED.value
                    self._write_step_json(step_folder, step_meta)
                    self._append_runs_row(exp, combo, step_folder, step_meta, "completed_no_imaging", None)
                case CameraResultStatus.ABORTED:
                    step_meta["status"] = StepStatus.ABORTED.value
                    step_meta["camera_status"] = CameraStatus.ABORTED.value
                    self._write_step_json(step_folder, step_meta)
                    self._append_runs_row(exp, combo, step_folder, step_meta, "aborted", None)
                    return self._final_status_after_break(), None
                case CameraResultStatus.FAILED:
                    step_meta["status"] = StepStatus.CAMERA_FAILED.value
                    step_meta["camera_status"] = CameraStatus.FAILED.value
                    step_meta["camera_error"] = result.error
                    self._write_step_json(step_folder, step_meta)
                    self._append_runs_row(exp, combo, step_folder, step_meta,
                                          "camera_failed", result.error)
                    return ExperimentStatus.FAILED, f"camera failed at combo {combo.combo_index}"

        return ExperimentStatus.COMPLETED, None

    def _wait(self, seconds: float) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self._stop.is_set() or self._error.is_set():
                return True
            time.sleep(0.05)
        return False

    def _final_status_after_break(self) -> ExperimentStatus:
        if self._error.is_set():
            return ExperimentStatus.FAILED
        return ExperimentStatus.ABORTED

    def _stabilization_for(self, changed: str) -> float:
        t = self._cfg.timing
        if changed in ("initial", "rpm"):
            return t.stabilization_rpm_change_s
        if changed == "freq":
            return t.stabilization_freq_change_s
        return t.stabilization_amp_change_s

    def _initial_step_meta(
        self, combo: SweepCombination, step_folder: Path
    ) -> dict[str, Any]:
        return {
            "combo_index": combo.combo_index,
            "set_speed_rpm": combo.set_speed_rpm,
            "set_frequency_hz": combo.frequency_hz,
            "set_amplitude_vpp": combo.amplitude_vpp,
            "changed": combo.changed,
            "hold_s": combo.hold_s,
            "stabilization_s": self._stabilization_for(combo.changed),
            "image_interval_s": self._cfg.timing.image_interval_s,
            "camera_latency_tolerance_s": self._cfg.timing.camera_latency_tolerance_s,
            "start_time_utc": utc_now_iso(),
            "status": StepStatus.PLANNED.value,
            "camera_status": CameraStatus.NOT_STARTED.value,
            "captures": 0,
            "pump_csv": "pump.csv",
            "oscilloscope_csv": "oscilloscope.csv",
            "scale_csv": "../../scale.csv",
        }

    def _write_step_json(self, folder: Path, payload: dict[str, Any]) -> None:
        ExperimentDirectory.write_json(folder / "step.json", payload)

    def _append_runs_row(
        self,
        exp: ExperimentDirectory,
        combo: SweepCombination,
        step_folder: Path,
        step_meta: dict[str, Any],
        status: str,
        failure_reason: str | None,
    ) -> None:
        exp.append_runs_row(
            RunsRow(
                timestamp_utc=utc_now_iso(),
                combo_index=combo.combo_index,
                experiment_id=self._cfg.experiment_id,
                nozzle_id=self._cfg.nozzle_id,
                set_speed_rpm=combo.set_speed_rpm,
                set_frequency_hz=combo.frequency_hz,
                set_amplitude_vpp=combo.amplitude_vpp,
                hold_s=combo.hold_s,
                step_folder=str(step_folder.relative_to(exp.root)),
                status=status,
                n_captures=int(step_meta.get("captures", 0)),
                failure_reason=failure_reason,
            )
        )

    def _write_experiment_json(
        self,
        exp: ExperimentDirectory,
        *,
        status: ExperimentStatus,
        failure_reason: str | None = None,
    ) -> None:
        payload = self._cfg.model_dump(mode="json")
        payload["status"] = status.value
        payload["failure_reason"] = failure_reason
        payload["initial_weight_g"] = self._initial_weight_g
        payload["written_at_utc"] = utc_now_iso()
        ExperimentDirectory.write_json(exp.root / "experiment.json", payload)
```

- [ ] **Step 7.2: Skip running the integration test for now** — it's stale; we replace it in Task 9. Confirm only that the orchestrator imports cleanly:

Run: `uv run python -c "from droplet_lab.orchestrator import Orchestrator"`
Expected: no error.

- [ ] **Step 7.3: Commit.**

```bash
git add src/droplet_lab/orchestrator.py
git -c commit.gpgsign=false commit -m "Orchestrator drives sweep cross-product and function generator"
```

---

## Task 8: CLI — imports, simulate-only, scaffolder, summary output

**Files:**
- Modify: `src/droplet_lab/cli.py`
- Modify: `tests/cli/test_cli.py`

### Step 8.1: Rewrite `src/droplet_lab/cli.py`

- [ ] Use this:

```python
"""Command-line interface (typer).

Subcommands:
    droplet run <yaml>             - run an experiment
    droplet validate <yaml>        - validate config without touching hardware
    droplet new <yaml-path>        - scaffold a new experiment YAML
    droplet list-devices           - list serial ports + VISA resources
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from droplet_lab import __version__
from droplet_lab.config import (
    CameraConfig,
    DevicesConfig,
    ExperimentConfig,
    FunctionGeneratorConfig,
    LimitsConfig,
    OscilloscopeConfig,
    OutputConfig,
    PumpConfig,
    ScaleConfig,
    SweepConfig,
    TimingConfig,
    VibrometerConfig,
    load_experiment,
)
from droplet_lab.devices import (
    build_camera,
    build_function_generator,
    build_oscilloscope,
    build_pump,
    build_scale,
)
from droplet_lab.orchestrator import DeviceBundle, Orchestrator
from droplet_lab.state import ExperimentState, ExperimentStatus
from droplet_lab.sweep import expand_sweep

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"droplet {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit",
        ),
    ] = False,
) -> None:
    """Droplet Lab controller."""


def _combo_count(cfg: ExperimentConfig) -> int:
    return (
        len(cfg.sweep.speeds_rpm)
        * len(cfg.sweep.frequencies_hz)
        * len(cfg.sweep.amplitudes_vpp)
    )


@app.command()
def validate(yaml_path: Path) -> None:
    """Validate an experiment YAML without opening any hardware."""
    cfg = load_experiment(yaml_path)
    typer.echo(f"OK: {cfg.experiment_id} ({_combo_count(cfg)} combinations)")


_VALID_SIMULATE_ONLY = {"pump", "scope", "camera", "function_generator", "scale"}


def _parse_simulate_only(raw: str | None) -> set[str]:
    if not raw:
        return set()
    items = {part.strip() for part in raw.split(",") if part.strip()}
    invalid = items - _VALID_SIMULATE_ONLY
    if invalid:
        raise typer.BadParameter(
            f"unknown device(s): {sorted(invalid)}; valid: {sorted(_VALID_SIMULATE_ONLY)}"
        )
    return items


@app.command()
def run(
    yaml_path: Path,
    simulate: Annotated[
        bool,
        typer.Option(
            "--simulate",
            help="Use all fake devices (pump, scope, camera, function_generator, scale)",
        ),
    ] = False,
    simulate_only: Annotated[
        str | None,
        typer.Option(
            "--simulate-only",
            help="Comma-separated list of devices to mock "
            "(pump,scope,camera,function_generator,scale)",
        ),
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option(help="Override output.base_dir"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print the plan and exit"),
    ] = False,
    no_confirm: Annotated[
        bool,
        typer.Option("--no-confirm", help="Skip 'press Enter to start'"),
    ] = False,
    no_tui: Annotated[
        bool,
        typer.Option("--no-tui", help="Disable rich live display"),
    ] = False,
) -> None:
    """Run an experiment."""
    cfg = load_experiment(yaml_path)
    if output_dir is not None:
        cfg = cfg.model_copy(update={"output": OutputConfig(base_dir=output_dir)})

    fakes = _parse_simulate_only(simulate_only)
    if simulate:
        fakes = set(_VALID_SIMULATE_ONLY)

    n_combos = _combo_count(cfg)
    typer.echo(f"Experiment: {cfg.experiment_id}  nozzle={cfg.nozzle_id}")
    typer.echo(
        f"Sweep: rpm={list(cfg.sweep.speeds_rpm)}  "
        f"freq={list(cfg.sweep.frequencies_hz)} Hz  "
        f"amp={list(cfg.sweep.amplitudes_vpp)} Vpp  "
        f"hold={cfg.sweep.hold_s} s  ({n_combos} combinations)"
    )
    if fakes:
        typer.echo(f"Simulated devices: {sorted(fakes)}")

    if dry_run:
        for c in expand_sweep(
            speeds_rpm=list(cfg.sweep.speeds_rpm),
            frequencies_hz=list(cfg.sweep.frequencies_hz),
            amplitudes_vpp=list(cfg.sweep.amplitudes_vpp),
            hold_s=cfg.sweep.hold_s,
        ):
            typer.echo(
                f"  combo {c.combo_index:03d}: rpm={c.set_speed_rpm}  "
                f"freq={c.frequency_hz}Hz  amp={c.amplitude_vpp}Vpp  "
                f"(changed={c.changed})"
            )
        typer.echo("--dry-run: not executing")
        return

    if not no_confirm:
        typer.confirm("Start experiment now?", abort=True)

    state = ExperimentState()
    devices: DeviceBundle = {
        "pump": build_pump(cfg.devices.pump, simulate="pump" in fakes),
        "scope": build_oscilloscope(
            cfg.devices.oscilloscope, state=state, simulate="scope" in fakes
        ),
        "camera": build_camera(cfg.devices.camera, simulate="camera" in fakes),
        "function_generator": build_function_generator(
            cfg.devices.function_generator,
            simulate="function_generator" in fakes,
        ),
        "scale": build_scale(cfg.devices.scale, simulate="scale" in fakes),
    }
    result = Orchestrator(
        config=cfg,
        devices=devices,
        state=state,
        install_signal_handler=True,
    ).run()

    typer.echo(f"\nresult: {result.status.value}")
    typer.echo(f"output: {result.experiment_dir.root}")
    if result.failure_reason:
        typer.echo(f"reason: {result.failure_reason}")
    if result.status is not ExperimentStatus.COMPLETED:
        raise typer.Exit(code=1)


@app.command()
def new(yaml_path: Path) -> None:
    """Scaffold a new experiment YAML at ``yaml_path`` with sensible defaults."""
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    cfg = ExperimentConfig(
        experiment_id=yaml_path.stem,
        nozzle_id="1mm_A",
        vibrometer=VibrometerConfig(factor_um_per_v=5280),
        sweep=SweepConfig(
            speeds_rpm=[200, 800, 1000],
            frequencies_hz=[20.0, 25.0, 30.0],
            amplitudes_vpp=[3.0, 5.0, 9.0],
            hold_s=30.0,
        ),
        timing=TimingConfig(
            stabilization_rpm_change_s=10.0,
            stabilization_freq_change_s=3.0,
            stabilization_amp_change_s=1.0,
            image_interval_s=5.0,
            camera_latency_tolerance_s=1.0,
        ),
        limits=LimitsConfig(max_speed_rpm=1000),
        devices=DevicesConfig(
            pump=PumpConfig(port="COM3"),
            oscilloscope=OscilloscopeConfig(visa_resource="USB0::0xXXXX::INSTR"),
            camera=CameraConfig(),
            function_generator=FunctionGeneratorConfig(port="COM4"),
            scale=ScaleConfig(enabled=False),
        ),
        output=OutputConfig(base_dir=Path("DATA")),
    )
    import yaml as _yaml

    yaml_path.write_text(_yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False))
    typer.echo(f"created {yaml_path}")


@app.command("list-devices")
def list_devices() -> None:
    """List available serial ports and VISA resources."""
    typer.echo("Serial ports:")
    try:
        from serial.tools import list_ports

        for p in list_ports.comports():
            typer.echo(f"  {p.device}  {p.description}")
    except Exception as e:
        typer.echo(f"  (error: {e})")

    typer.echo("VISA resources:")
    try:
        import pyvisa

        rm = pyvisa.ResourceManager()
        for r in rm.list_resources():
            typer.echo(f"  {r}")
        rm.close()
    except Exception as e:
        typer.echo(f"  (error: {e})")
```

### Step 8.2: Update CLI tests

- [ ] Read the existing tests, then update them:

Run: `cat tests/cli/test_cli.py`

Patch the following:

- Anywhere `ramp`/`actuation` appears in test YAML — replace with the new `sweep`/`vibrometer` blocks (use the same shape as `_minimal_dict` in `tests/unit/test_config.py`).
- For any test of `--simulate-only`: add a case asserting that `function_generator` is accepted.
- For any test of unknown device: assert that the error message lists `function_generator` as valid.

Add these tests:

```python
from pathlib import Path

import yaml
from typer.testing import CliRunner

from droplet_lab.cli import app


def _write_minimal_yaml(tmp_path: Path) -> Path:
    data = {
        "experiment_id": "TEST_01",
        "nozzle_id": "1mm_A",
        "vibrometer": {"factor_um_per_v": 5280},
        "sweep": {
            "speeds_rpm": [200],
            "frequencies_hz": [20.0],
            "amplitudes_vpp": [3.0],
            "hold_s": 1.0,
        },
        "timing": {
            "stabilization_rpm_change_s": 0.5,
            "stabilization_freq_change_s": 0.2,
            "stabilization_amp_change_s": 0.1,
            "image_interval_s": 0.5,
            "camera_latency_tolerance_s": 0.5,
        },
        "limits": {"max_speed_rpm": 1000},
        "devices": {
            "pump": {"port": "COM3"},
            "oscilloscope": {"visa_resource": "USB0::INSTR"},
            "camera": {"digicam_url": "http://localhost:5513"},
            "function_generator": {"port": "COM4", "channel": 1},
            "scale": {"enabled": False},
        },
        "output": {"base_dir": str(tmp_path)},
    }
    path = tmp_path / "exp.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_simulate_only_accepts_function_generator(tmp_path: Path) -> None:
    runner = CliRunner()
    yaml_path = _write_minimal_yaml(tmp_path)
    result = runner.invoke(
        app,
        [
            "run", str(yaml_path),
            "--simulate-only", "function_generator",
            "--no-confirm", "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output


def test_simulate_only_rejects_unknown_device(tmp_path: Path) -> None:
    runner = CliRunner()
    yaml_path = _write_minimal_yaml(tmp_path)
    result = runner.invoke(app, ["run", str(yaml_path), "--simulate-only", "bogus"])
    assert result.exit_code != 0
    assert "bogus" in result.output
    assert "function_generator" in result.output


def test_validate_reports_combination_count(tmp_path: Path) -> None:
    runner = CliRunner()
    yaml_path = _write_minimal_yaml(tmp_path)
    result = runner.invoke(app, ["validate", str(yaml_path)])
    assert result.exit_code == 0, result.output
    assert "1 combinations" in result.output
```

- [ ] Run:

Run: `uv run pytest tests/cli/ -v`
Expected: all pass.

- [ ] **Step 8.3: Commit.**

```bash
git add src/droplet_lab/cli.py tests/cli/
git -c commit.gpgsign=false commit -m "CLI: drive sweep, add function_generator simulate-only choice, update scaffolder"
```

---

## Task 9: Example YAML + end-to-end integration test + green build

**Files:**
- Replace: `experiments/example_hpmc.yaml`
- Create: `experiments/example_sweep_mini.yaml`
- Replace: `tests/integration/test_orchestrator_end_to_end.py`

### Step 9.1: Replace `experiments/example_hpmc.yaml`

- [ ] Write:

```yaml
# Reference experiment. Copy and edit for new runs.
experiment_id: HPMC_Test_01
nozzle_id: 1mm_A

vibrometer:
  factor_um_per_v: 5280

# Full cross product is fired in order: rpm outermost, then frequency, then amplitude.
sweep:
  speeds_rpm:     [200, 800, 1000]
  frequencies_hz: [20, 25, 30]
  amplitudes_vpp: [3.0, 5.0, 9.0]
  hold_s: 30                          # per combination

timing:
  stabilization_rpm_change_s: 10
  stabilization_freq_change_s: 3
  stabilization_amp_change_s: 1
  image_interval_s: 5
  camera_latency_tolerance_s: 1.0

limits:
  max_speed_rpm: 1000

devices:
  pump:
    port: COM3
    baudrate: 9600
  oscilloscope:
    visa_resource: "USB0::0x2A8D::0x1778::MY55440264::0::INSTR"
  camera:
    digicam_url: "http://localhost:5513"
  function_generator:
    port: COM4
    channel: 1
    baudrate: 115200
  scale:
    enabled: false
    baudrate: 1200
    interval_s: 5

output:
  base_dir: 'W:\PROMOTION_SHARIFSOLTANI_VERKAPSELUNG_DFG_TH1817_9_1_MT\PYTHON\Project_files\DATA'
```

### Step 9.2: Create `experiments/example_sweep_mini.yaml` for the integration test

- [ ] Write:

```yaml
experiment_id: SWEEP_MINI
nozzle_id: 1mm_A

vibrometer:
  factor_um_per_v: 5280

sweep:
  speeds_rpm:     [200, 300]
  frequencies_hz: [20.0, 25.0]
  amplitudes_vpp: [3.0, 5.0]
  hold_s: 1.0

timing:
  stabilization_rpm_change_s: 0.2
  stabilization_freq_change_s: 0.1
  stabilization_amp_change_s: 0.05
  image_interval_s: 0.2
  camera_latency_tolerance_s: 0.5

limits:
  max_speed_rpm: 1000

devices:
  pump:
    port: COMX
    baudrate: 9600
  oscilloscope:
    visa_resource: "USBX::INSTR"
  camera:
    digicam_url: "http://localhost:5513"
  function_generator:
    port: COMY
    channel: 1
  scale:
    enabled: true
    port: COMZ
    baudrate: 1200
    interval_s: 0.2

output:
  base_dir: ./DATA  # overridden in tests via output_dir
```

### Step 9.3: Rewrite `tests/integration/test_orchestrator_end_to_end.py`

- [ ] First read the existing file to understand fixtures and helpers (esp. `conftest.py`):

Run: `cat tests/integration/test_orchestrator_end_to_end.py`
Run: `cat tests/integration/conftest.py`

- [ ] Then replace with a new sweep-aware test that:
  1. Loads `experiments/example_sweep_mini.yaml` and overrides `output.base_dir` to `tmp_path`.
  2. Builds all-fake devices (`build_*(simulate=True)`).
  3. Runs the orchestrator.
  4. Asserts:
     - Result status is `COMPLETED`.
     - 8 combo folders exist in correct order (`combo_001_rpm0200_f20Hz_amp3V` … `combo_008_rpm0300_f25Hz_amp5V`).
     - Each combo folder has `pump.csv`, `oscilloscope.csv`, `step.json`, `images/`.
     - `scale.csv` exists in root, header includes `phase`, first data row has `phase=initial`, second has `phase=sweep`.
     - `runs.csv` has 8 data rows, all `status=completed`.
     - The fake function generator received exactly the sequence of calls expected — capture the fake via the device bundle.
     - `experiment.json` contains `initial_weight_g` (not null) and `status: completed`.

Here is a complete reference implementation:

```python
from pathlib import Path

import pytest
import yaml

from droplet_lab.config import OutputConfig, load_experiment
from droplet_lab.devices import (
    FakeCamera,
    FakeFunctionGenerator,
    FakeOscilloscope,
    FakePump,
    FakeScale,
)
from droplet_lab.orchestrator import DeviceBundle, Orchestrator
from droplet_lab.state import ExperimentState, ExperimentStatus


def _load_mini(tmp_path: Path):
    cfg = load_experiment(Path("experiments/example_sweep_mini.yaml"))
    return cfg.model_copy(update={"output": OutputConfig(base_dir=tmp_path)})


def test_sweep_runs_end_to_end_on_fakes(tmp_path: Path) -> None:
    cfg = _load_mini(tmp_path)
    state = ExperimentState()
    fake_pump = FakePump(acceleration_rpm_per_s=10000)
    fake_scope = FakeOscilloscope(state=state)
    fake_camera = FakeCamera()
    fake_fg = FakeFunctionGenerator()
    fake_scale = FakeScale()
    devices: DeviceBundle = {
        "pump": fake_pump,
        "scope": fake_scope,
        "camera": fake_camera,
        "function_generator": fake_fg,
        "scale": fake_scale,
    }
    result = Orchestrator(config=cfg, devices=devices, state=state).run()
    assert result.status is ExperimentStatus.COMPLETED, result.failure_reason

    root = result.experiment_dir.root
    # 1. 8 combo folders, in order.
    combos = sorted((root / "steps").iterdir())
    names = [c.name for c in combos]
    assert names == [
        "combo_001_rpm0200_f20Hz_amp3V",
        "combo_002_rpm0200_f20Hz_amp5V",
        "combo_003_rpm0200_f25Hz_amp3V",
        "combo_004_rpm0200_f25Hz_amp5V",
        "combo_005_rpm0300_f20Hz_amp3V",
        "combo_006_rpm0300_f20Hz_amp5V",
        "combo_007_rpm0300_f25Hz_amp3V",
        "combo_008_rpm0300_f25Hz_amp5V",
    ]
    for folder in combos:
        assert (folder / "step.json").exists()
        assert (folder / "pump.csv").exists(), folder
        assert (folder / "oscilloscope.csv").exists(), folder
        assert (folder / "images").is_dir()

    # 2. scale.csv with initial + sweep rows.
    scale_text = (root / "scale.csv").read_text().splitlines()
    assert "phase" in scale_text[0]
    assert scale_text[1].split(";")[2] == "initial"
    assert any(line.split(";")[2] == "sweep" for line in scale_text[2:])

    # 3. runs.csv has 8 completed rows.
    runs_lines = (root / "runs.csv").read_text().splitlines()
    assert runs_lines[0].startswith("timestamp_utc;")
    assert len(runs_lines) == 9  # header + 8
    for line in runs_lines[1:]:
        assert ";completed;" in line, line

    # 4. function generator received the expected sequence.
    #    Filter to (set_frequency_hz, set_amplitude_vpp, enable_output) calls,
    #    ignoring the initial set_sine + enable_output(False).
    keep = {"set_frequency_hz", "set_amplitude_vpp", "enable_output"}
    relevant = [c for c in fake_fg.calls if c[0] in keep]
    # Drop the very first enable_output(False) preface.
    assert relevant[0:1] == [("enable_output", False)] or relevant[0] != ("enable_output", False)
    # Expected freq/amp sequence (one freq per (rpm,freq) start, amp every combo):
    expected_freq_amp = [
        ("set_frequency_hz", 20.0), ("set_amplitude_vpp", 3.0), ("enable_output", True),
        ("set_amplitude_vpp", 5.0),
        ("set_frequency_hz", 25.0), ("set_amplitude_vpp", 3.0),
        ("set_amplitude_vpp", 5.0),
        ("set_frequency_hz", 20.0), ("set_amplitude_vpp", 3.0),
        ("set_amplitude_vpp", 5.0),
        ("set_frequency_hz", 25.0), ("set_amplitude_vpp", 3.0),
        ("set_amplitude_vpp", 5.0),
    ]
    # Strip leading bookkeeping (set_sine + enable_output(False)).
    trimmed = [c for c in fake_fg.calls if c[0] in keep]
    # The very first relevant entry should be enable_output(False) from __enter__.
    assert ("enable_output", False) in trimmed
    # Remove all leading enable_output(False) entries to align with expected_freq_amp.
    idx = trimmed.index(("set_frequency_hz", 20.0))
    assert trimmed[idx:idx + len(expected_freq_amp)] == expected_freq_amp

    # 5. experiment.json captures initial_weight_g.
    import json
    payload = json.loads((root / "experiment.json").read_text())
    assert payload["status"] == "completed"
    assert payload["initial_weight_g"] is not None
```

- [ ] Run the full test suite:

Run: `uv run pytest -v`
Expected: all tests pass.

- [ ] Run lint + types:

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src tests`
Expected: clean. (If `ruff format --check` fails, run `uv run ruff format .` and re-stage.)

- [ ] Run the example YAML through the validator:

Run: `uv run droplet validate experiments/example_hpmc.yaml`
Expected: `OK: HPMC_Test_01 (27 combinations)`.

- [ ] Run a full simulated experiment:

Run: `uv run droplet run experiments/example_sweep_mini.yaml --simulate --no-confirm --output-dir /tmp/droplet_test`
Expected: completes with status `completed` and prints the output dir.

- [ ] **Step 9.4: Commit.**

```bash
git add experiments/ tests/integration/
git -c commit.gpgsign=false commit -m "Update example YAML to sweep schema and add end-to-end sweep integration test"
```

---

## Final Self-Review Checklist

- [ ] `uv run pytest` → all green
- [ ] `uv run ruff check .` → clean
- [ ] `uv run ruff format --check .` → clean
- [ ] `uv run mypy src tests` → clean
- [ ] `uv run droplet validate experiments/example_hpmc.yaml` → OK
- [ ] `uv run droplet run experiments/example_sweep_mini.yaml --simulate --no-confirm --output-dir /tmp/droplet_test` → completed
- [ ] Spot-check `/tmp/droplet_test/<run>/steps/combo_001_*/` — `step.json`, `pump.csv`, `oscilloscope.csv`, `images/` present
- [ ] Spot-check `/tmp/droplet_test/<run>/runs.csv` and `scale.csv`
- [ ] No references to `RampStep`, `ActuationConfig`, `_walk_ramp`, `create_step_folder`, `step_index` outside of historical commits
