# Droplet Lab Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the four-script, file-IPC droplet-generation control system with a single typed Python 3.12 package (`droplet_lab`) that runs experiments declaratively from YAML, simulates hardware end-to-end, and is fully covered by tests.

**Architecture:** Single process; one thread per long-running device worker (pump, oscilloscope) plus a per-step camera worker with a watchdog; coordination via `queue.Queue` and `threading.Event`; hardware behind `typing.Protocol` with paired `Real*` / `Fake*` implementations.

**Tech Stack:** Python 3.12, `uv`, `pyproject.toml` (PEP 621), `pydantic` v2 + `pyyaml`, `typer`, `loguru`, `pyserial`, `pyvisa`, `requests`, `pytest` + `pytest-cov`, `ruff`, `mypy --strict`, `pre-commit`, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-05-02-droplet-lab-refactor-design.md`

---

## Conventions used in this plan

- **Working directory** for all shell commands: repository root `/Users/sariman/repos/droplet-generation-setup-controller`.
- **Manual commits.** The user signs commits manually. Each task ends with a "Stage and commit" step that lists files to stage and a suggested message; the engineer runs `git add ...` but does **not** run `git commit` — the user commits.
- **TDD where it bites.** Tests are written first for any module containing logic. For scaffolding (config files), there is nothing to test — those tasks have no test step. For Real device wrappers, "tests" are mock-based (`unittest.mock` patching `serial.Serial` / `pyvisa.ResourceManager` / `requests.get`).
- **Run tests via** `uv run pytest`, lint via `uv run ruff check`, types via `uv run mypy src`. After every implementation step, run the relevant test before moving on.

---

## Task 1: Project bootstrap (`pyproject.toml`, Python pin, gitignore)

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Modify: `.gitignore`

- [ ] **Step 1: Pin Python version**

Create `.python-version`:

```
3.12
```

- [ ] **Step 2: Create `pyproject.toml`**

Create `pyproject.toml`:

```toml
[project]
name = "droplet-lab"
version = "0.1.0"
description = "Lab controller for droplet-generation experiments (pump + oscilloscope + camera + scale)."
readme = "README.md"
requires-python = ">=3.12"
license = { text = "MIT" }
authors = [{ name = "Droplet Lab" }]
dependencies = [
    "pydantic>=2.7",
    "pyyaml>=6.0",
    "typer>=0.12",
    "loguru>=0.7",
    "rich>=13.7",
    "pyserial>=3.5",
    "pyvisa>=1.14",
    "requests>=2.32",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2",
    "pytest-cov>=5.0",
    "ruff>=0.5",
    "mypy>=1.10",
    "types-requests",
    "types-pyyaml",
    "pre-commit>=3.7",
]

[project.scripts]
droplet = "droplet_lab.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/droplet_lab"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "N", "RUF"]
ignore = ["E501"]

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.12"
strict = true
warn_unreachable = true
warn_redundant_casts = true
files = ["src", "tests"]

[[tool.mypy.overrides]]
module = ["pyvisa.*", "serial.*"]
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = ["tests.*"]
disallow_untyped_defs = false
disallow_incomplete_defs = false

[tool.pytest.ini_options]
addopts = "-ra --strict-markers --strict-config"
testpaths = ["tests"]
markers = [
    "hardware: requires real lab hardware (skipped by default)",
]
```

- [ ] **Step 3: Update `.gitignore`**

Replace `.gitignore` with:

```
# Experiment outputs
DATA/

# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
.eggs/
build/
dist/
.venv/
venv/

# Test / coverage
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/
.ruff_cache/

# OS / editor
.DS_Store
.vscode/
.idea/
```

- [ ] **Step 4: Initialize venv and verify**

Run:
```bash
uv venv
uv pip install -e ".[dev]"
uv run python -c "import sys; print(sys.version)"
```
Expected: prints a `3.12.x` version.

- [ ] **Step 5: Stage**

```bash
git add pyproject.toml .python-version .gitignore
```

Suggested commit message: `chore: bootstrap pyproject + pin Python 3.12`

---

## Task 2: Pre-commit and CI configs

**Files:**
- Create: `.pre-commit-config.yaml`
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-yaml
      - id: check-toml
      - id: check-merge-conflict

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies:
          - pydantic>=2.7
          - types-requests
          - types-pyyaml
        args: [--strict]
        files: ^(src|tests)/
```

- [ ] **Step 2: Create `.github/workflows/ci.yml`**

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - name: Install Python
        run: uv python install 3.12
      - name: Sync deps
        run: uv sync --all-extras
      - name: Lint
        run: uv run ruff check .
      - name: Format check
        run: uv run ruff format --check .
      - name: Type check
        run: uv run mypy src tests
      - name: Tests
        run: uv run pytest --cov=droplet_lab --cov-report=term-missing
```

- [ ] **Step 3: Stage**

```bash
git add .pre-commit-config.yaml .github/workflows/ci.yml
```

Suggested commit message: `ci: add pre-commit + GitHub Actions matrix (linux/mac/windows)`

---

## Task 3: Package skeleton (`src/droplet_lab/__init__.py` and `__main__.py`)

**Files:**
- Create: `src/droplet_lab/__init__.py`
- Create: `src/droplet_lab/__main__.py`

- [ ] **Step 1: Create package init**

Create `src/droplet_lab/__init__.py`:

```python
"""Droplet generation lab controller."""

__version__ = "0.1.0"
```

- [ ] **Step 2: Create module entry point**

Create `src/droplet_lab/__main__.py`:

```python
"""Allows `python -m droplet_lab` to invoke the CLI."""

from droplet_lab.cli import app


def main() -> None:
    app()


if __name__ == "__main__":
    main()
```

(The `cli` module is created in Task 17. mypy will currently fail on this import — that's fine, it'll resolve once Task 17 lands. If you want to keep the tree green, comment out the import and re-enable in Task 17.)

- [ ] **Step 3: Stage**

```bash
git add src/droplet_lab/__init__.py src/droplet_lab/__main__.py
```

Suggested commit message: `feat: add droplet_lab package skeleton`

---

## Task 4: State module (`state.py`) — enums + ExperimentState dataclass

**Files:**
- Create: `src/droplet_lab/state.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/unit/test_state.py`

- [ ] **Step 1: Write failing tests**

Create `tests/__init__.py` (empty) and `tests/unit/__init__.py` (empty).

Create `tests/unit/test_state.py`:

```python
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
    assert state.step_index is None
    assert state.set_speed_rpm is None


def test_experiment_state_update_is_thread_safe() -> None:
    import threading

    state = ExperimentState()

    def writer(start: int) -> None:
        for i in range(start, start + 100):
            state.update(step_index=i, set_speed_rpm=i * 10)

    threads = [threading.Thread(target=writer, args=(i * 1000,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    snapshot = state.snapshot()
    assert snapshot.step_index is not None
    assert snapshot.set_speed_rpm is not None
    assert snapshot.set_speed_rpm == snapshot.step_index * 10
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/unit/test_state.py -v`
Expected: ImportError / ModuleNotFoundError for `droplet_lab.state`.

- [ ] **Step 3: Implement `state.py`**

Create `src/droplet_lab/state.py`:

```python
"""Status enums and the shared ExperimentState dataclass."""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from enum import StrEnum


class ExperimentStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


class StepStatus(StrEnum):
    PLANNED = "planned"
    STABILIZING = "stabilizing"
    IMAGING = "imaging"
    COMPLETED = "completed"
    COMPLETED_NO_IMAGING = "completed_no_imaging"
    CAMERA_TIMEOUT = "camera_timeout"
    CAMERA_FAILED = "camera_failed"
    ABORTED = "aborted"


class CameraStatus(StrEnum):
    NOT_STARTED = "not_started"
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


@dataclass(frozen=True, slots=True)
class ExperimentStateSnapshot:
    """Immutable point-in-time view of ExperimentState (safe to share across threads)."""

    step_index: int | None = None
    set_speed_rpm: int | None = None


class ExperimentState:
    """Thread-safe holder for the orchestrator's currently active step + speed.

    Workers (especially the scope) read this every measurement to tag rows with
    the correct step. The orchestrator updates it on every ramp transition.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot = ExperimentStateSnapshot()

    @property
    def step_index(self) -> int | None:
        with self._lock:
            return self._snapshot.step_index

    @property
    def set_speed_rpm(self) -> int | None:
        with self._lock:
            return self._snapshot.set_speed_rpm

    def update(self, *, step_index: int, set_speed_rpm: int) -> None:
        with self._lock:
            self._snapshot = replace(
                self._snapshot,
                step_index=step_index,
                set_speed_rpm=set_speed_rpm,
            )

    def snapshot(self) -> ExperimentStateSnapshot:
        with self._lock:
            return self._snapshot
```

- [ ] **Step 4: Verify the tests pass**

Run: `uv run pytest tests/unit/test_state.py -v`
Expected: 3 passed.

- [ ] **Step 5: Type-check**

Run: `uv run mypy src/droplet_lab/state.py tests/unit/test_state.py`
Expected: `Success: no issues found`.

- [ ] **Step 6: Stage**

```bash
git add src/droplet_lab/state.py tests/__init__.py tests/unit/__init__.py tests/unit/test_state.py
```

Suggested commit message: `feat(state): add status enums and thread-safe ExperimentState`

---

## Task 5: Config module (`config.py`) — Pydantic v2 models

**Files:**
- Create: `src/droplet_lab/config.py`
- Create: `tests/unit/test_config.py`
- Create: `experiments/example_hpmc.yaml`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_config.py`:

```python
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from droplet_lab.config import (
    ActuationConfig,
    CameraConfig,
    DevicesConfig,
    ExperimentConfig,
    LimitsConfig,
    OscilloscopeConfig,
    OutputConfig,
    PumpConfig,
    RampStep,
    ScaleConfig,
    TimingConfig,
    load_experiment,
)


def _minimal_dict(tmp_path: Path) -> dict[str, object]:
    return {
        "experiment_id": "TEST_01",
        "nozzle_id": "1mm_A",
        "actuation": {
            "frequency_hz": 200,
            "voltage_v": 5,
            "vibrometer_factor_um_per_v": 5280,
        },
        "ramp": [
            {"speed_rpm": 200, "hold_s": 1.0},
            {"speed_rpm": 250, "hold_s": 1.0},
        ],
        "timing": {
            "stabilization_s": 0.1,
            "image_interval_s": 0.5,
            "camera_latency_tolerance_s": 0.5,
        },
        "limits": {"max_speed_rpm": 1000},
        "devices": {
            "pump": {"port": "COM3", "baudrate": 9600},
            "oscilloscope": {"visa_resource": "USB0::INSTR"},
            "camera": {"digicam_url": "http://localhost:5513"},
            "scale": {"enabled": False},
        },
        "output": {"base_dir": str(tmp_path)},
    }


def test_minimal_config_validates(tmp_path: Path) -> None:
    cfg = ExperimentConfig.model_validate(_minimal_dict(tmp_path))
    assert cfg.experiment_id == "TEST_01"
    assert cfg.actuation.frequency_hz == 200
    assert len(cfg.ramp) == 2
    assert cfg.devices.scale.enabled is False
    assert cfg.output.base_dir == tmp_path.resolve()


def test_ramp_step_rejects_zero_speed() -> None:
    with pytest.raises(ValidationError):
        RampStep(speed_rpm=0, hold_s=1.0)


def test_ramp_step_rejects_negative_hold() -> None:
    with pytest.raises(ValidationError):
        RampStep(speed_rpm=200, hold_s=-1.0)


def test_ramp_must_not_be_empty(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    data["ramp"] = []
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(data)


def test_ramp_speed_must_not_exceed_limit(tmp_path: Path) -> None:
    data = _minimal_dict(tmp_path)
    data["ramp"] = [{"speed_rpm": 1500, "hold_s": 1.0}]  # limit is 1000
    with pytest.raises(ValidationError) as exc:
        ExperimentConfig.model_validate(data)
    assert "max_speed_rpm" in str(exc.value)


def test_unknown_field_is_rejected(tmp_path: Path) -> None:
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


def test_actuation_rejects_zero_frequency() -> None:
    with pytest.raises(ValidationError):
        ActuationConfig(frequency_hz=0, voltage_v=5, vibrometer_factor_um_per_v=5280)


def test_pump_config_defaults() -> None:
    cfg = PumpConfig(port="COM3")
    assert cfg.baudrate == 9600


def test_scale_disabled_by_default() -> None:
    cfg = ScaleConfig()
    assert cfg.enabled is False
    assert cfg.port is None


def test_devices_config_partial(tmp_path: Path) -> None:
    devices = DevicesConfig(
        pump=PumpConfig(port="COM3"),
        oscilloscope=OscilloscopeConfig(visa_resource="USB0::INSTR"),
        camera=CameraConfig(digicam_url="http://localhost:5513"),
        scale=ScaleConfig(),
    )
    assert devices.scale.enabled is False


def test_example_yaml_validates() -> None:
    """The shipped example YAML must always validate."""
    cfg = load_experiment(Path("experiments/example_hpmc.yaml"))
    assert cfg.experiment_id


def test_output_config_resolves_path(tmp_path: Path) -> None:
    cfg = OutputConfig(base_dir=tmp_path)
    assert cfg.base_dir.is_absolute()
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: ImportError on `droplet_lab.config`.

- [ ] **Step 3: Implement `config.py`**

Create `src/droplet_lab/config.py`:

```python
"""Pydantic v2 models for experiment configuration.

A complete experiment is one YAML file under ``experiments/``. ``load_experiment``
parses, validates, and returns an ``ExperimentConfig``. Any structural problem in
the YAML (typo, wrong type, missing field, value out of range) raises
``ValidationError`` with a precise location.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

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


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ActuationConfig(_StrictModel):
    frequency_hz: PositiveFloat
    voltage_v: PositiveFloat
    vibrometer_factor_um_per_v: PositiveFloat


class RampStep(_StrictModel):
    speed_rpm: PositiveInt
    hold_s: PositiveFloat


class TimingConfig(_StrictModel):
    stabilization_s: NonNegativeFloat
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


class ScaleConfig(_StrictModel):
    enabled: bool = False
    port: str | None = None
    baudrate: PositiveInt = 9600


class DevicesConfig(_StrictModel):
    pump: PumpConfig
    oscilloscope: OscilloscopeConfig
    camera: CameraConfig
    scale: ScaleConfig = Field(default_factory=ScaleConfig)


class OutputConfig(_StrictModel):
    base_dir: Path

    @field_validator("base_dir", mode="after")
    @classmethod
    def _resolve(cls, value: Path) -> Path:
        return value.expanduser().resolve()


RampProfile = Annotated[list[RampStep], Field(min_length=1)]


class ExperimentConfig(_StrictModel):
    experiment_id: str = Field(min_length=1)
    nozzle_id: str = Field(min_length=1)
    actuation: ActuationConfig
    ramp: RampProfile
    timing: TimingConfig
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    devices: DevicesConfig
    output: OutputConfig

    @model_validator(mode="after")
    def _ramp_within_limits(self) -> ExperimentConfig:
        max_rpm = self.limits.max_speed_rpm
        for i, step in enumerate(self.ramp):
            if step.speed_rpm > max_rpm:
                raise ValueError(
                    f"ramp[{i}].speed_rpm={step.speed_rpm} exceeds "
                    f"limits.max_speed_rpm={max_rpm}"
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

- [ ] **Step 4: Create the example YAML**

Create `experiments/example_hpmc.yaml`:

```yaml
# Reference experiment. Copy and edit for new runs.
experiment_id: HPMC_Test_01
nozzle_id: 1mm_A

actuation:
  frequency_hz: 200            # Hz
  voltage_v: 5                 # V
  vibrometer_factor_um_per_v: 5280   # um per V

# Each step holds the pump at speed_rpm for hold_s seconds.
# Imaging duration per step is hold_s - timing.stabilization_s.
ramp:
  - { speed_rpm: 200, hold_s: 30 }
  - { speed_rpm: 250, hold_s: 30 }
  - { speed_rpm: 300, hold_s: 60 }
  - { speed_rpm: 350, hold_s: 60 }
  - { speed_rpm: 400, hold_s: 120 }

timing:
  stabilization_s: 10
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
  scale:
    enabled: false

output:
  base_dir: 'W:\PROMOTION_SHARIFSOLTANI_VERKAPSELUNG_DFG_TH1817_9_1_MT\PYTHON\Project_files\DATA'
```

- [ ] **Step 5: Verify tests pass**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: 12 passed.

- [ ] **Step 6: Type-check**

Run: `uv run mypy src/droplet_lab/config.py tests/unit/test_config.py`
Expected: `Success`.

- [ ] **Step 7: Stage**

```bash
git add src/droplet_lab/config.py tests/unit/test_config.py experiments/example_hpmc.yaml
```

Suggested commit message: `feat(config): add validated YAML schema for experiments`

---

## Task 6: Storage module (`storage.py`) — directory layout + CSV writers

**Files:**
- Create: `src/droplet_lab/storage.py`
- Create: `tests/unit/test_storage.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_storage.py`:

```python
import csv
import json
from pathlib import Path

import pytest

from droplet_lab.storage import (
    ExperimentDirectory,
    OscilloscopeRow,
    PumpRow,
    ScaleRow,
    sanitize_filename,
    utc_now_iso,
)


def test_sanitize_filename_replaces_invalid_chars() -> None:
    assert sanitize_filename("a/b\\c:d*e?f") == "a_b_c_d_e_f"
    assert sanitize_filename("hello world") == "hello_world"
    assert sanitize_filename("  trim me  ") == "trim_me"


def test_utc_now_iso_format() -> None:
    s = utc_now_iso()
    assert s.endswith("Z")
    assert "T" in s
    # parse round-trip
    from datetime import datetime
    datetime.fromisoformat(s.replace("Z", "+00:00"))


def test_experiment_directory_creates_layout(tmp_path: Path) -> None:
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="TEST 01")
    assert exp.root.exists()
    assert exp.root.parent == tmp_path
    assert "TEST_01" in exp.root.name
    assert exp.steps_dir.exists()


def test_experiment_directory_step_folder(tmp_path: Path) -> None:
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    folder = exp.create_step_folder(step_index=3, set_speed_rpm=350)
    assert folder.exists()
    assert folder.name == "step_03_350rpm"
    assert (folder / "images").exists()


def test_pump_csv_writer_writes_header_and_rows(tmp_path: Path) -> None:
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    with exp.open_pump_csv() as writer:
        writer.write(
            PumpRow(
                timestamp_utc="2026-05-02T10:00:00.000000Z",
                elapsed_s=0.0,
                step_index=1,
                set_speed_rpm=200,
                actual_speed_rpm=199,
                temperature_c=23.5,
            )
        )
        writer.write(
            PumpRow(
                timestamp_utc="2026-05-02T10:00:05.000000Z",
                elapsed_s=5.0,
                step_index=1,
                set_speed_rpm=200,
                actual_speed_rpm=200,
                temperature_c=23.6,
            )
        )

    rows = list(csv.DictReader((exp.root / "pump.csv").open(), delimiter=";"))
    assert len(rows) == 2
    assert rows[0]["set_speed_rpm"] == "200"
    assert rows[1]["temperature_c"] == "23.6"


def test_oscilloscope_csv_writer_handles_none_values(tmp_path: Path) -> None:
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    with exp.open_oscilloscope_csv() as writer:
        writer.write(
            OscilloscopeRow(
                timestamp_utc="2026-05-02T10:00:00.000000Z",
                elapsed_s=0.0,
                step_index=None,
                set_speed_rpm=None,
                frequency_hz=None,
                vpp_v=None,
                p2p_displacement_um=None,
                ch2_vrms_dc_v=None,
                ch3_vrms_dc_v=None,
            )
        )
    text = (exp.root / "oscilloscope.csv").read_text()
    # None must serialize as empty cell
    assert text.split("\n")[1].split(";").count("") >= 8


def test_scale_csv_writer(tmp_path: Path) -> None:
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    with exp.open_scale_csv() as writer:
        writer.write(
            ScaleRow(
                timestamp_utc="2026-05-02T10:00:00.000000Z",
                elapsed_s=0.0,
                step_index=1,
                set_speed_rpm=200,
                weight_g=12.34,
            )
        )
    rows = list(csv.DictReader((exp.root / "scale.csv").open(), delimiter=";"))
    assert rows[0]["weight_g"] == "12.34"


def test_write_json_pretty(tmp_path: Path) -> None:
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    payload = {"a": 1, "nested": {"b": 2}}
    exp.write_json(exp.root / "experiment.json", payload)
    loaded = json.loads((exp.root / "experiment.json").read_text())
    assert loaded == payload
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/unit/test_storage.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `storage.py`**

Create `src/droplet_lab/storage.py`:

```python
"""Output directory layout and CSV writers.

Every experiment writes into one timestamped folder under ``base_dir``::

    <base_dir>/<UTC-timestamp>__<experiment_id>/
        experiment.json
        experiment.log
        pump.csv
        oscilloscope.csv
        scale.csv          (only if scale enabled)
        steps/
            step_01_200rpm/
                step.json
                images/
            step_02_250rpm/
                ...

CSVs use ``;`` separators (DE-Excel friendly) and UTF-8.
All timestamps are UTC ISO 8601 with microsecond precision and a trailing ``Z``.
"""

from __future__ import annotations

import csv
import json
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, Iterator


_INVALID_FILENAME_CHARS = '<>:"/\\|?*'


def sanitize_filename(text: str) -> str:
    """Strip characters that aren't safe in filenames; collapse whitespace to ``_``."""
    out = text
    for ch in _INVALID_FILENAME_CHARS:
        out = out.replace(ch, "_")
    return out.strip().replace(" ", "_")


def utc_now_iso() -> str:
    """UTC timestamp in ISO 8601 with microseconds and a ``Z`` suffix."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def utc_now_filename_safe() -> str:
    """UTC timestamp with characters that survive Windows path rules."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")


# -------- CSV row dataclasses --------


@dataclass(frozen=True, slots=True)
class PumpRow:
    timestamp_utc: str
    elapsed_s: float
    step_index: int | None
    set_speed_rpm: int | None
    actual_speed_rpm: int | None
    temperature_c: float | None


@dataclass(frozen=True, slots=True)
class OscilloscopeRow:
    timestamp_utc: str
    elapsed_s: float
    step_index: int | None
    set_speed_rpm: int | None
    frequency_hz: float | None
    vpp_v: float | None
    p2p_displacement_um: float | None
    ch2_vrms_dc_v: float | None
    ch3_vrms_dc_v: float | None


@dataclass(frozen=True, slots=True)
class ScaleRow:
    timestamp_utc: str
    elapsed_s: float
    step_index: int | None
    set_speed_rpm: int | None
    weight_g: float | None


# -------- CSV writer wrapper --------


class CsvRowWriter:
    """Writes dataclass rows to a CSV file (semicolon-separated, UTF-8)."""

    def __init__(self, fp: IO[str], fieldnames: list[str]) -> None:
        self._fp = fp
        self._writer = csv.DictWriter(fp, fieldnames=fieldnames, delimiter=";")
        self._writer.writeheader()
        fp.flush()

    def write(self, row: Any) -> None:
        data = asdict(row)
        # Serialize None as empty cells instead of "None"
        sanitized = {k: ("" if v is None else v) for k, v in data.items()}
        self._writer.writerow(sanitized)
        self._fp.flush()


# -------- Experiment directory --------


@dataclass(frozen=True, slots=True)
class ExperimentDirectory:
    """Filesystem layout for one experiment run."""

    root: Path

    @property
    def steps_dir(self) -> Path:
        return self.root / "steps"

    @classmethod
    def create(cls, *, base_dir: Path, experiment_id: str) -> ExperimentDirectory:
        base_dir.mkdir(parents=True, exist_ok=True)
        folder = base_dir / f"{utc_now_filename_safe()}__{sanitize_filename(experiment_id)}"
        folder.mkdir()
        (folder / "steps").mkdir()
        return cls(root=folder)

    def create_step_folder(self, *, step_index: int, set_speed_rpm: int) -> Path:
        folder = self.steps_dir / f"step_{step_index:02d}_{set_speed_rpm}rpm"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "images").mkdir(exist_ok=True)
        return folder

    @contextmanager
    def open_pump_csv(self) -> Iterator[CsvRowWriter]:
        with (self.root / "pump.csv").open("w", encoding="utf-8", newline="") as fp:
            yield CsvRowWriter(
                fp,
                [
                    "timestamp_utc",
                    "elapsed_s",
                    "step_index",
                    "set_speed_rpm",
                    "actual_speed_rpm",
                    "temperature_c",
                ],
            )

    @contextmanager
    def open_oscilloscope_csv(self) -> Iterator[CsvRowWriter]:
        with (self.root / "oscilloscope.csv").open("w", encoding="utf-8", newline="") as fp:
            yield CsvRowWriter(
                fp,
                [
                    "timestamp_utc",
                    "elapsed_s",
                    "step_index",
                    "set_speed_rpm",
                    "frequency_hz",
                    "vpp_v",
                    "p2p_displacement_um",
                    "ch2_vrms_dc_v",
                    "ch3_vrms_dc_v",
                ],
            )

    @contextmanager
    def open_scale_csv(self) -> Iterator[CsvRowWriter]:
        with (self.root / "scale.csv").open("w", encoding="utf-8", newline="") as fp:
            yield CsvRowWriter(
                fp,
                [
                    "timestamp_utc",
                    "elapsed_s",
                    "step_index",
                    "set_speed_rpm",
                    "weight_g",
                ],
            )

    @staticmethod
    def write_json(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
```

- [ ] **Step 4: Verify the tests pass**

Run: `uv run pytest tests/unit/test_storage.py -v`
Expected: 8 passed.

- [ ] **Step 5: Type-check**

Run: `uv run mypy src/droplet_lab/storage.py tests/unit/test_storage.py`
Expected: `Success`.

- [ ] **Step 6: Stage**

```bash
git add src/droplet_lab/storage.py tests/unit/test_storage.py
```

Suggested commit message: `feat(storage): add experiment directory layout + CSV writers`

---

## Task 7: Logging setup (`logging_setup.py`)

**Files:**
- Create: `src/droplet_lab/logging_setup.py`
- Create: `tests/unit/test_logging_setup.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_logging_setup.py`:

```python
from pathlib import Path

from loguru import logger

from droplet_lab.logging_setup import setup_logging


def test_setup_creates_log_file_and_writes(tmp_path: Path) -> None:
    log_file = setup_logging(tmp_path, level="DEBUG")
    logger.bind(component="test").info("hello world")
    logger.complete()  # flush async sinks

    assert log_file.exists()
    content = log_file.read_text()
    assert "hello world" in content
    assert "test" in content


def test_setup_is_idempotent(tmp_path: Path) -> None:
    setup_logging(tmp_path)
    setup_logging(tmp_path)  # must not crash
    logger.bind(component="x").info("ok")
    logger.complete()
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/unit/test_logging_setup.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `logging_setup.py`**

Create `src/droplet_lab/logging_setup.py`:

```python
"""Loguru configuration for droplet_lab.

Two sinks:

* **Console** at INFO+, colored, terse format.
* **File** ``<experiment_dir>/experiment.log`` at DEBUG+, full format with
  source location and UTC timestamps. ``enqueue=True`` makes it safe to write
  from multiple threads.

Each thread should bind a ``component`` extra::

    logger.bind(component="pump").info("set speed to 200")
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

_CONSOLE_FORMAT = (
    "<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | "
    "<cyan>{extra[component]: <12}</cyan> | {message}"
)
_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS!UTC} | {level: <8} | "
    "{extra[component]: <12} | {name}:{function}:{line} | {message}"
)


def setup_logging(experiment_dir: Path, *, level: str = "INFO") -> Path:
    """Configure loguru sinks. Returns the path to the file sink."""
    logger.remove()
    logger.configure(extra={"component": "main"})

    logger.add(
        sys.stderr,
        level=level,
        format=_CONSOLE_FORMAT,
        backtrace=False,
        diagnose=False,
    )

    log_file = experiment_dir / "experiment.log"
    logger.add(
        log_file,
        level="DEBUG",
        format=_FILE_FORMAT,
        enqueue=True,
        backtrace=True,
        diagnose=False,
        rotation=None,
    )
    return log_file
```

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest tests/unit/test_logging_setup.py -v`
Expected: 2 passed.

- [ ] **Step 5: Stage**

```bash
git add src/droplet_lab/logging_setup.py tests/unit/test_logging_setup.py
```

Suggested commit message: `feat(logging): add loguru console + file sinks per experiment`

---

## Task 8: Device protocols (`devices/base.py`)

**Files:**
- Create: `src/droplet_lab/devices/__init__.py`
- Create: `src/droplet_lab/devices/base.py`
- Create: `tests/devices/__init__.py`
- Create: `tests/devices/test_base.py`

- [ ] **Step 1: Write a failing test (structural)**

Create `tests/devices/__init__.py` (empty).

Create `tests/devices/test_base.py`:

```python
"""Smoke tests that prove the protocols + measurement dataclasses are importable
and that measurement dataclasses are immutable."""

from dataclasses import FrozenInstanceError

import pytest

from droplet_lab.devices.base import (
    Camera,
    Oscilloscope,
    Pump,
    Scale,
    ScopeMeasurement,
)


def test_protocols_are_importable() -> None:
    assert Pump is not None
    assert Oscilloscope is not None
    assert Camera is not None
    assert Scale is not None


def test_scope_measurement_is_frozen() -> None:
    m = ScopeMeasurement(
        frequency_hz=200.0,
        vpp_v=1.0,
        ch2_vrms_dc_v=0.5,
        ch3_vrms_dc_v=0.5,
    )
    with pytest.raises(FrozenInstanceError):
        m.frequency_hz = 300.0  # type: ignore[misc]
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/devices/test_base.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `devices/__init__.py`**

Create `src/droplet_lab/devices/__init__.py`:

```python
"""Hardware device abstractions and factories."""

from droplet_lab.devices.base import (
    Camera,
    Oscilloscope,
    Pump,
    Scale,
    ScopeMeasurement,
)

__all__ = [
    "Camera",
    "Oscilloscope",
    "Pump",
    "Scale",
    "ScopeMeasurement",
]
```

- [ ] **Step 4: Implement `devices/base.py`**

Create `src/droplet_lab/devices/base.py`:

```python
"""Protocols and value objects for hardware devices.

Every device class has a typed ``Protocol`` that doubles as a context manager.
Real implementations (``MZR7245Pump`` etc.) and fakes (``FakePump`` etc.) both
satisfy the protocol structurally — no inheritance needed.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ScopeMeasurement:
    """One sample from the oscilloscope. ``None`` means the channel/measurement failed."""

    frequency_hz: float | None
    vpp_v: float | None
    ch2_vrms_dc_v: float | None
    ch3_vrms_dc_v: float | None


class Pump(Protocol, AbstractContextManager["Pump"]):
    def set_speed(self, rpm: int) -> None: ...
    def stop(self) -> None: ...
    def get_actual_speed_rpm(self) -> int | None: ...
    def get_target_speed_rpm(self) -> int | None: ...
    def get_temperature_c(self) -> float | None: ...


class Oscilloscope(Protocol, AbstractContextManager["Oscilloscope"]):
    def identify(self) -> str: ...
    def measure(self) -> ScopeMeasurement: ...


class Camera(Protocol, AbstractContextManager["Camera"]):
    def set_output_folder(self, folder: Path) -> None: ...
    def trigger_capture(self) -> None: ...


class Scale(Protocol, AbstractContextManager["Scale"]):
    def read_weight_g(self) -> float | None: ...
```

- [ ] **Step 5: Verify the tests pass**

Run: `uv run pytest tests/devices/test_base.py -v`
Expected: 2 passed.

- [ ] **Step 6: Type-check**

Run: `uv run mypy src/droplet_lab/devices`
Expected: `Success`.

- [ ] **Step 7: Stage**

```bash
git add src/droplet_lab/devices/__init__.py src/droplet_lab/devices/base.py tests/devices/__init__.py tests/devices/test_base.py
```

Suggested commit message: `feat(devices): define typed Protocols + ScopeMeasurement`

---

## Task 9: FakePump

**Files:**
- Create: `src/droplet_lab/devices/pump_fake.py`
- Create: `tests/devices/test_pump_fake.py`

- [ ] **Step 1: Write failing tests**

Create `tests/devices/test_pump_fake.py`:

```python
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
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/devices/test_pump_fake.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `pump_fake.py`**

Create `src/droplet_lab/devices/pump_fake.py`:

```python
"""In-memory pump simulator for tests and dry runs.

Models RPM as first-order approach to target with constant acceleration limit,
and temperature as a slow log-normal drift correlated with running speed.
Deterministic given a seed.
"""

from __future__ import annotations

import math
import random
from types import TracebackType


class FakePump:
    """Drop-in replacement for the real pump. No serial, no hardware."""

    def __init__(
        self,
        *,
        seed: int = 0,
        acceleration_rpm_per_s: float = 200.0,
        ambient_temp_c: float = 22.0,
    ) -> None:
        self._rng = random.Random(seed)
        self._accel = acceleration_rpm_per_s
        self._target_rpm: int = 0
        self._actual_rpm: float = 0.0
        self._temp_c: float = ambient_temp_c
        self._ambient = ambient_temp_c
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    def __enter__(self) -> "FakePump":
        self._open = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._open = False

    def set_speed(self, rpm: int) -> None:
        if rpm < 0:
            raise ValueError(f"rpm must be >= 0, got {rpm}")
        self._target_rpm = rpm

    def stop(self) -> None:
        self._target_rpm = 0

    def get_actual_speed_rpm(self) -> int | None:
        return int(round(self._actual_rpm))

    def get_target_speed_rpm(self) -> int | None:
        return self._target_rpm

    def get_temperature_c(self) -> float | None:
        return round(self._temp_c, 2)

    def advance(self, seconds: float) -> None:
        """Advance the simulator clock (test helper, not on Protocol)."""
        delta = self._target_rpm - self._actual_rpm
        max_change = self._accel * seconds
        if abs(delta) <= max_change:
            self._actual_rpm = float(self._target_rpm)
        else:
            self._actual_rpm += math.copysign(max_change, delta)

        # Heat up when running, cool toward ambient otherwise.
        load = self._actual_rpm / 1000.0
        equilibrium = self._ambient + 25.0 * load
        self._temp_c += (equilibrium - self._temp_c) * min(1.0, seconds * 0.05)
        self._temp_c += self._rng.uniform(-0.05, 0.05) * seconds
```

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest tests/devices/test_pump_fake.py -v`
Expected: 8 passed.

- [ ] **Step 5: Stage**

```bash
git add src/droplet_lab/devices/pump_fake.py tests/devices/test_pump_fake.py
```

Suggested commit message: `feat(devices): add FakePump simulator (deterministic)`

---

## Task 10: Real pump (`pump_mzr7245.py`)

**Files:**
- Create: `src/droplet_lab/devices/pump_mzr7245.py`
- Create: `tests/devices/test_pump_mzr7245.py`

- [ ] **Step 1: Write failing mock-based tests**

Create `tests/devices/test_pump_mzr7245.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from droplet_lab.devices.pump_mzr7245 import MZR7245Pump


@pytest.fixture
def fake_serial() -> MagicMock:
    s = MagicMock()
    s.is_open = True
    s.read_all.return_value = b""
    return s


def test_context_manager_opens_and_closes(fake_serial: MagicMock) -> None:
    with patch("droplet_lab.devices.pump_mzr7245.serial.Serial", return_value=fake_serial):
        with MZR7245Pump(port="COM3", baudrate=9600) as pump:
            assert pump is not None
        fake_serial.close.assert_called_once()


def test_set_speed_writes_v_command(fake_serial: MagicMock) -> None:
    with patch("droplet_lab.devices.pump_mzr7245.serial.Serial", return_value=fake_serial):
        with MZR7245Pump(port="COM3") as pump:
            pump.set_speed(250)
        fake_serial.write.assert_any_call(b"V250\r")


def test_stop_writes_v0(fake_serial: MagicMock) -> None:
    with patch("droplet_lab.devices.pump_mzr7245.serial.Serial", return_value=fake_serial):
        with MZR7245Pump(port="COM3") as pump:
            pump.stop()
        fake_serial.write.assert_any_call(b"V0\r")


def test_get_actual_speed_parses_int(fake_serial: MagicMock) -> None:
    fake_serial.read_all.return_value = b"199\r\n"
    with patch("droplet_lab.devices.pump_mzr7245.serial.Serial", return_value=fake_serial):
        with MZR7245Pump(port="COM3") as pump:
            assert pump.get_actual_speed_rpm() == 199


def test_get_actual_speed_returns_none_on_garbage(fake_serial: MagicMock) -> None:
    fake_serial.read_all.return_value = b"???"
    with patch("droplet_lab.devices.pump_mzr7245.serial.Serial", return_value=fake_serial):
        with MZR7245Pump(port="COM3") as pump:
            assert pump.get_actual_speed_rpm() is None


def test_satisfies_pump_protocol(fake_serial: MagicMock) -> None:
    from droplet_lab.devices.base import Pump

    with patch("droplet_lab.devices.pump_mzr7245.serial.Serial", return_value=fake_serial):
        pump: Pump = MZR7245Pump(port="COM3")
        assert pump is not None
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/devices/test_pump_mzr7245.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `pump_mzr7245.py`**

Create `src/droplet_lab/devices/pump_mzr7245.py`:

```python
"""Ismatec MZR-7245 gear pump driver over RS-232.

Command set used:
    V<rpm>  -- set target speed
    GN      -- query actual speed (rpm)
    GV      -- query target speed (rpm)
    TEM     -- query temperature (degrees C)
"""

from __future__ import annotations

import time
from types import TracebackType

import serial
from loguru import logger


def _safe_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return None


class MZR7245Pump:
    def __init__(
        self,
        *,
        port: str,
        baudrate: int = 9600,
        timeout_s: float = 1.0,
        post_open_delay_s: float = 2.0,
    ) -> None:
        self._port = port
        self._baudrate = baudrate
        self._timeout_s = timeout_s
        self._post_open_delay_s = post_open_delay_s
        self._ser: serial.Serial | None = None
        self._log = logger.bind(component="pump")

    def __enter__(self) -> "MZR7245Pump":
        self._ser = serial.Serial(
            port=self._port,
            baudrate=self._baudrate,
            timeout=self._timeout_s,
        )
        time.sleep(self._post_open_delay_s)
        self._log.info("opened pump on {} @ {} baud", self._port, self._baudrate)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._ser is not None and self._ser.is_open:
            try:
                self._ser.close()
            finally:
                self._log.info("closed pump")
        self._ser = None

    def _cmd(self, command: str, pause: float = 0.2) -> str | None:
        if self._ser is None:
            raise RuntimeError("Pump is not open")
        self._ser.reset_input_buffer()
        self._ser.write((command + "\r").encode("ascii"))
        self._ser.flush()
        time.sleep(pause)
        raw = self._ser.read_all() or b""
        reply = raw.decode("ascii", errors="replace").strip()
        self._log.debug("cmd {!r} -> {!r}", command, reply)
        return reply or None

    def set_speed(self, rpm: int) -> None:
        if rpm < 0:
            raise ValueError(f"rpm must be >= 0, got {rpm}")
        self._cmd(f"V{int(rpm)}")

    def stop(self) -> None:
        self._cmd("V0")

    def get_actual_speed_rpm(self) -> int | None:
        return _safe_int(self._cmd("GN"))

    def get_target_speed_rpm(self) -> int | None:
        return _safe_int(self._cmd("GV"))

    def get_temperature_c(self) -> float | None:
        raw = self._cmd("TEM")
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError:
            return None
```

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest tests/devices/test_pump_mzr7245.py -v`
Expected: 6 passed.

- [ ] **Step 5: Type-check**

Run: `uv run mypy src/droplet_lab/devices/pump_mzr7245.py`
Expected: `Success`.

- [ ] **Step 6: Stage**

```bash
git add src/droplet_lab/devices/pump_mzr7245.py tests/devices/test_pump_mzr7245.py
```

Suggested commit message: `feat(devices): add MZR7245Pump (pyserial driver)`

---

## Task 11: FakeOscilloscope

**Files:**
- Create: `src/droplet_lab/devices/oscilloscope_fake.py`
- Create: `tests/devices/test_oscilloscope_fake.py`

- [ ] **Step 1: Write failing tests**

Create `tests/devices/test_oscilloscope_fake.py`:

```python
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
    state.update(step_index=1, set_speed_rpm=300)
    with FakeOscilloscope(state=state, seed=0) as scope:
        m = scope.measure()
        assert m.frequency_hz is not None and m.frequency_hz > 0
        assert m.vpp_v is not None and m.vpp_v > 0
        assert m.ch2_vrms_dc_v is not None
        assert m.ch3_vrms_dc_v is not None


def test_vpp_increases_with_rpm() -> None:
    state = ExperimentState()
    with FakeOscilloscope(state=state, seed=0, noise_amplitude=0.0) as scope:
        state.update(step_index=1, set_speed_rpm=100)
        low = scope.measure().vpp_v
        state.update(step_index=2, set_speed_rpm=900)
        high = scope.measure().vpp_v
    assert low is not None and high is not None
    assert high > low


def test_determinism() -> None:
    state = ExperimentState()
    state.update(step_index=1, set_speed_rpm=200)
    a = FakeOscilloscope(state=state, seed=7)
    b = FakeOscilloscope(state=state, seed=7)
    with a, b:
        assert a.measure() == b.measure()
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/devices/test_oscilloscope_fake.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `oscilloscope_fake.py`**

Create `src/droplet_lab/devices/oscilloscope_fake.py`:

```python
"""In-memory oscilloscope simulator. Generates measurements correlated with the
current ``ExperimentState`` so end-to-end tests see meaningful CSV rows.
"""

from __future__ import annotations

import random
from types import TracebackType

from droplet_lab.devices.base import ScopeMeasurement
from droplet_lab.state import ExperimentState


class FakeOscilloscope:
    def __init__(
        self,
        *,
        state: ExperimentState,
        seed: int = 0,
        noise_amplitude: float = 0.02,
    ) -> None:
        self._state = state
        self._rng = random.Random(seed)
        self._noise = noise_amplitude
        self._open = False

    def __enter__(self) -> "FakeOscilloscope":
        self._open = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._open = False

    def identify(self) -> str:
        return "FakeOscilloscope (droplet_lab simulator)"

    def measure(self) -> ScopeMeasurement:
        rpm = self._state.set_speed_rpm or 0
        noise = self._rng.uniform(-self._noise, self._noise)
        vpp = max(0.0, 0.001 * rpm + 0.05 + noise)
        return ScopeMeasurement(
            frequency_hz=200.0 + noise * 5.0,
            vpp_v=round(vpp, 6),
            ch2_vrms_dc_v=round(0.5 + noise * 0.2, 6),
            ch3_vrms_dc_v=round(0.5 + noise * 0.2, 6),
        )
```

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest tests/devices/test_oscilloscope_fake.py -v`
Expected: 5 passed.

- [ ] **Step 5: Stage**

```bash
git add src/droplet_lab/devices/oscilloscope_fake.py tests/devices/test_oscilloscope_fake.py
```

Suggested commit message: `feat(devices): add FakeOscilloscope correlated with ExperimentState`

---

## Task 12: Real oscilloscope (`oscilloscope_keysight.py`)

**Files:**
- Create: `src/droplet_lab/devices/oscilloscope_keysight.py`
- Create: `tests/devices/test_oscilloscope_keysight.py`

- [ ] **Step 1: Write failing mock-based tests**

Create `tests/devices/test_oscilloscope_keysight.py`:

```python
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
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/devices/test_oscilloscope_keysight.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `oscilloscope_keysight.py`**

Create `src/droplet_lab/devices/oscilloscope_keysight.py`:

```python
"""Keysight DSOX oscilloscope driver via VISA / SCPI."""

from __future__ import annotations

import math
from types import TracebackType

import pyvisa
from loguru import logger

from droplet_lab.devices.base import ScopeMeasurement


_KEYSIGHT_INVALID_SENTINEL = 9.9e37  # scope returns ~9.91E+37 when no signal


def _safe_float(text: str) -> float | None:
    try:
        value = float(text.strip())
    except (ValueError, AttributeError):
        return None
    if math.isnan(value) or math.isinf(value) or abs(value) >= _KEYSIGHT_INVALID_SENTINEL:
        return None
    return value


class KeysightOscilloscope:
    def __init__(
        self,
        *,
        visa_resource: str,
        timeout_ms: int = 5000,
    ) -> None:
        self._resource = visa_resource
        self._timeout_ms = timeout_ms
        self._rm: pyvisa.ResourceManager | None = None
        self._scope: pyvisa.resources.MessageBasedResource | None = None
        self._log = logger.bind(component="scope")

    def __enter__(self) -> "KeysightOscilloscope":
        self._rm = pyvisa.ResourceManager()
        self._scope = self._rm.open_resource(self._resource)
        self._scope.timeout = self._timeout_ms
        self._scope.write_termination = "\n"
        self._scope.read_termination = "\n"
        self._log.info("opened scope at {}", self._resource)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._scope is not None:
            try:
                self._scope.close()
            except Exception:  # noqa: BLE001 - cleanup must not raise
                pass
        if self._rm is not None:
            try:
                self._rm.close()
            except Exception:  # noqa: BLE001
                pass
        self._scope = None
        self._rm = None
        self._log.info("closed scope")

    def _query(self, scpi: str) -> str:
        if self._scope is None:
            raise RuntimeError("Oscilloscope is not open")
        return self._scope.query(scpi)

    def identify(self) -> str:
        return self._query("*IDN?").strip()

    def measure(self) -> ScopeMeasurement:
        return ScopeMeasurement(
            frequency_hz=_safe_float(self._query(":MEASure:FREQuency? CHANnel1")),
            vpp_v=_safe_float(self._query(":MEASure:VPP? CHANnel1")),
            ch2_vrms_dc_v=_safe_float(self._query(":MEASure:VRMS? DISPlay,DC,CHANnel2")),
            ch3_vrms_dc_v=_safe_float(self._query(":MEASure:VRMS? DISPlay,DC,CHANnel3")),
        )
```

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest tests/devices/test_oscilloscope_keysight.py -v`
Expected: 4 passed.

- [ ] **Step 5: Stage**

```bash
git add src/droplet_lab/devices/oscilloscope_keysight.py tests/devices/test_oscilloscope_keysight.py
```

Suggested commit message: `feat(devices): add KeysightOscilloscope (pyvisa driver)`

---

## Task 13: FakeCamera

**Files:**
- Create: `src/droplet_lab/devices/camera_fake.py`
- Create: `tests/devices/test_camera_fake.py`

- [ ] **Step 1: Write failing tests**

Create `tests/devices/test_camera_fake.py`:

```python
from pathlib import Path

import pytest

from droplet_lab.devices.camera_fake import FakeCamera


def test_satisfies_protocol() -> None:
    from droplet_lab.devices.base import Camera
    c: Camera = FakeCamera()
    assert c is not None


def test_trigger_writes_file(tmp_path: Path) -> None:
    with FakeCamera() as cam:
        cam.set_output_folder(tmp_path)
        cam.trigger_capture()
        cam.trigger_capture()
    files = sorted(tmp_path.glob("*.NEF"))
    assert len(files) == 2
    assert files[0].name == "FAKE_0001.NEF"
    assert files[1].name == "FAKE_0002.NEF"


def test_trigger_without_folder_raises() -> None:
    with FakeCamera() as cam:
        with pytest.raises(RuntimeError):
            cam.trigger_capture()


def test_can_be_configured_to_fail(tmp_path: Path) -> None:
    cam = FakeCamera(fail_after_triggers=2)
    with cam:
        cam.set_output_folder(tmp_path)
        cam.trigger_capture()
        cam.trigger_capture()
        with pytest.raises(RuntimeError, match="injected"):
            cam.trigger_capture()


def test_can_be_configured_to_hang(tmp_path: Path) -> None:
    import time
    cam = FakeCamera(hang_after_triggers=1, hang_seconds=0.2)
    with cam:
        cam.set_output_folder(tmp_path)
        cam.trigger_capture()
        start = time.monotonic()
        cam.trigger_capture()
        assert time.monotonic() - start >= 0.2
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/devices/test_camera_fake.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `camera_fake.py`**

Create `src/droplet_lab/devices/camera_fake.py`:

```python
"""In-memory camera simulator that writes empty placeholder files.

Configurable failure injection (``fail_after_triggers``, ``hang_after_triggers``)
lets integration tests exercise watchdog and error paths.
"""

from __future__ import annotations

import time
from pathlib import Path
from types import TracebackType


class FakeCamera:
    def __init__(
        self,
        *,
        fail_after_triggers: int | None = None,
        hang_after_triggers: int | None = None,
        hang_seconds: float = 0.0,
    ) -> None:
        self._folder: Path | None = None
        self._counter = 0
        self._open = False
        self._fail_after = fail_after_triggers
        self._hang_after = hang_after_triggers
        self._hang_seconds = hang_seconds

    def __enter__(self) -> "FakeCamera":
        self._open = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._open = False

    def set_output_folder(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        self._folder = folder
        self._counter = 0

    def trigger_capture(self) -> None:
        if self._folder is None:
            raise RuntimeError("set_output_folder() must be called first")
        if self._fail_after is not None and self._counter >= self._fail_after:
            raise RuntimeError("injected failure (FakeCamera)")
        if self._hang_after is not None and self._counter >= self._hang_after:
            time.sleep(self._hang_seconds)
        self._counter += 1
        path = self._folder / f"FAKE_{self._counter:04d}.NEF"
        path.write_bytes(b"")
```

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest tests/devices/test_camera_fake.py -v`
Expected: 5 passed.

- [ ] **Step 5: Stage**

```bash
git add src/droplet_lab/devices/camera_fake.py tests/devices/test_camera_fake.py
```

Suggested commit message: `feat(devices): add FakeCamera with failure/hang injection`

---

## Task 14: Real camera (`camera_digicam.py`)

**Files:**
- Create: `src/droplet_lab/devices/camera_digicam.py`
- Create: `tests/devices/test_camera_digicam.py`

- [ ] **Step 1: Write failing mock-based tests**

Create `tests/devices/test_camera_digicam.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from droplet_lab.devices.camera_digicam import DigiCamCamera


def _ok_response() -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.text = "OK"
    r.raise_for_status = MagicMock()
    return r


def test_set_output_folder_calls_session_folder() -> None:
    with patch("droplet_lab.devices.camera_digicam.requests.get",
               return_value=_ok_response()) as get:
        with DigiCamCamera(url="http://localhost:5513") as cam:
            cam.set_output_folder(Path("C:/data/step_01"))
        # First call after enter is the set; assert it carries session.folder
        calls = [c.kwargs.get("params") for c in get.call_args_list]
        assert any(
            params and params.get("slc") == "set" and params.get("param1") == "session.folder"
            for params in calls
        )


def test_trigger_capture_calls_capture_endpoint() -> None:
    with patch("droplet_lab.devices.camera_digicam.requests.get",
               return_value=_ok_response()) as get:
        with DigiCamCamera(url="http://localhost:5513") as cam:
            cam.set_output_folder(Path("C:/data/step_01"))
            cam.trigger_capture()
        calls = [c.kwargs.get("params") for c in get.call_args_list]
        assert any(p and p.get("slc") == "capture" for p in calls)


def test_http_error_raises() -> None:
    bad = MagicMock()
    bad.raise_for_status.side_effect = RuntimeError("HTTP 500")
    with patch("droplet_lab.devices.camera_digicam.requests.get", return_value=bad):
        with DigiCamCamera(url="http://localhost:5513") as cam:
            cam.set_output_folder(Path("C:/x"))
            with pytest.raises(RuntimeError):
                cam.trigger_capture()
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/devices/test_camera_digicam.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `camera_digicam.py`**

Create `src/droplet_lab/devices/camera_digicam.py`:

```python
"""DigiCamControl HTTP client.

DigiCamControl exposes an HTTP server (default port 5513). Requests are
URL-parameterised commands; ``slc=set`` writes a property, ``slc=capture``
fires the shutter.

Reference: https://digicamcontrol.com/doc/userguide/web
"""

from __future__ import annotations

from pathlib import Path
from types import TracebackType

import requests
from loguru import logger


class DigiCamCamera:
    def __init__(
        self,
        *,
        url: str = "http://localhost:5513",
        request_timeout_s: float = 10.0,
    ) -> None:
        self._url = url
        self._timeout = request_timeout_s
        self._open = False
        self._log = logger.bind(component="camera")

    def __enter__(self) -> "DigiCamCamera":
        self._open = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._open = False

    def _get(self, params: dict[str, str]) -> None:
        response = requests.get(self._url, params=params, timeout=self._timeout)
        response.raise_for_status()

    def set_output_folder(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        self._get({"slc": "set", "param1": "session.folder", "param2": str(folder)})
        self._log.info("camera folder set to {}", folder)

    def trigger_capture(self) -> None:
        self._get({"slc": "capture", "param1": "", "param2": ""})
```

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest tests/devices/test_camera_digicam.py -v`
Expected: 3 passed.

- [ ] **Step 5: Stage**

```bash
git add src/droplet_lab/devices/camera_digicam.py tests/devices/test_camera_digicam.py
```

Suggested commit message: `feat(devices): add DigiCamCamera HTTP client`

---

## Task 15: FakeScale + RealSartoriusScale

**Files:**
- Create: `src/droplet_lab/devices/scale_fake.py`
- Create: `src/droplet_lab/devices/scale_sartorius.py`
- Create: `tests/devices/test_scale_fake.py`
- Create: `tests/devices/test_scale_sartorius.py`

- [ ] **Step 1: Write failing test for FakeScale**

Create `tests/devices/test_scale_fake.py`:

```python
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
```

- [ ] **Step 2: Verify the test fails**

Run: `uv run pytest tests/devices/test_scale_fake.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `scale_fake.py`**

Create `src/droplet_lab/devices/scale_fake.py`:

```python
"""In-memory scale simulator (monotonically increasing mass)."""

from __future__ import annotations

import random
from types import TracebackType


class FakeScale:
    def __init__(
        self,
        *,
        seed: int = 0,
        rate_g_per_s: float = 0.5,
        noise_g: float = 0.005,
    ) -> None:
        self._rng = random.Random(seed)
        self._rate = rate_g_per_s
        self._noise = noise_g
        self._weight = 0.0
        self._open = False

    def __enter__(self) -> "FakeScale":
        self._open = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._open = False

    def read_weight_g(self) -> float | None:
        return round(self._weight + self._rng.uniform(-self._noise, self._noise), 4)

    def advance(self, seconds: float) -> None:
        self._weight += self._rate * seconds
```

- [ ] **Step 4: Verify FakeScale tests pass**

Run: `uv run pytest tests/devices/test_scale_fake.py -v`
Expected: 3 passed.

- [ ] **Step 5: Write failing test for SartoriusScale**

Create `tests/devices/test_scale_sartorius.py`:

```python
from unittest.mock import MagicMock, patch

from droplet_lab.devices.scale_sartorius import SartoriusScale


def test_open_close() -> None:
    fake = MagicMock()
    with patch("droplet_lab.devices.scale_sartorius.serial.Serial", return_value=fake):
        with SartoriusScale(port="COM5"):
            pass
        fake.close.assert_called_once()


def test_read_weight_parses_print_line() -> None:
    fake = MagicMock()
    fake.readline.return_value = b"+   12.345 g\r\n"
    with patch("droplet_lab.devices.scale_sartorius.serial.Serial", return_value=fake):
        with SartoriusScale(port="COM5") as scale:
            assert scale.read_weight_g() == 12.345


def test_read_weight_returns_none_on_garbage() -> None:
    fake = MagicMock()
    fake.readline.return_value = b"???\r\n"
    with patch("droplet_lab.devices.scale_sartorius.serial.Serial", return_value=fake):
        with SartoriusScale(port="COM5") as scale:
            assert scale.read_weight_g() is None
```

- [ ] **Step 6: Verify the test fails**

Run: `uv run pytest tests/devices/test_scale_sartorius.py -v`
Expected: ImportError.

- [ ] **Step 7: Implement `scale_sartorius.py`**

Create `src/droplet_lab/devices/scale_sartorius.py`:

```python
"""Sartorius balance driver (RS-232, 7E1 framing).

The balance prints a line whenever ``PRINT`` is pressed or autoprint is enabled.
Lines look like ``"+   12.345 g\\r\\n"``. Sign and unit are stripped; we return
grams.
"""

from __future__ import annotations

import re
from types import TracebackType

import serial
from loguru import logger


_LINE_RE = re.compile(r"^\s*(?P<sign>[+-])?\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>[a-zA-Z]*)?")


class SartoriusScale:
    def __init__(
        self,
        *,
        port: str,
        baudrate: int = 9600,
        timeout_s: float = 1.0,
    ) -> None:
        self._port = port
        self._baudrate = baudrate
        self._timeout_s = timeout_s
        self._ser: serial.Serial | None = None
        self._log = logger.bind(component="scale")

    def __enter__(self) -> "SartoriusScale":
        self._ser = serial.Serial(
            port=self._port,
            baudrate=self._baudrate,
            bytesize=serial.SEVENBITS,
            parity=serial.PARITY_EVEN,
            stopbits=serial.STOPBITS_ONE,
            timeout=self._timeout_s,
        )
        self._log.info("opened scale on {}", self._port)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._ser is not None and self._ser.is_open:
            self._ser.close()
        self._ser = None

    def read_weight_g(self) -> float | None:
        if self._ser is None:
            raise RuntimeError("Scale is not open")
        line = self._ser.readline().decode("ascii", errors="replace")
        match = _LINE_RE.match(line)
        if match is None:
            return None
        try:
            value = float(match.group("value"))
        except ValueError:
            return None
        if match.group("sign") == "-":
            value = -value
        return value
```

- [ ] **Step 8: Verify SartoriusScale tests pass**

Run: `uv run pytest tests/devices/test_scale_sartorius.py -v`
Expected: 3 passed.

- [ ] **Step 9: Stage**

```bash
git add src/droplet_lab/devices/scale_fake.py src/droplet_lab/devices/scale_sartorius.py tests/devices/test_scale_fake.py tests/devices/test_scale_sartorius.py
```

Suggested commit message: `feat(devices): add Sartorius scale + fake counterpart`

---

## Task 16: Device factory (`devices/__init__.py` extension)

**Files:**
- Modify: `src/droplet_lab/devices/__init__.py`
- Create: `tests/devices/test_factory.py`

- [ ] **Step 1: Write failing tests**

Create `tests/devices/test_factory.py`:

```python
from droplet_lab.config import (
    CameraConfig,
    OscilloscopeConfig,
    PumpConfig,
    ScaleConfig,
)
from droplet_lab.devices import (
    build_camera,
    build_oscilloscope,
    build_pump,
    build_scale,
)
from droplet_lab.devices.camera_fake import FakeCamera
from droplet_lab.devices.oscilloscope_fake import FakeOscilloscope
from droplet_lab.devices.pump_fake import FakePump
from droplet_lab.devices.scale_fake import FakeScale
from droplet_lab.state import ExperimentState


def test_simulate_returns_fakes() -> None:
    pump = build_pump(PumpConfig(port="COM3"), simulate=True)
    scope = build_oscilloscope(
        OscilloscopeConfig(visa_resource="USB"),
        state=ExperimentState(),
        simulate=True,
    )
    cam = build_camera(CameraConfig(), simulate=True)
    scale = build_scale(ScaleConfig(enabled=True, port="COM5"), simulate=True)
    assert isinstance(pump, FakePump)
    assert isinstance(scope, FakeOscilloscope)
    assert isinstance(cam, FakeCamera)
    assert isinstance(scale, FakeScale)


def test_real_returns_real_classes() -> None:
    from droplet_lab.devices.camera_digicam import DigiCamCamera
    from droplet_lab.devices.oscilloscope_keysight import KeysightOscilloscope
    from droplet_lab.devices.pump_mzr7245 import MZR7245Pump
    from droplet_lab.devices.scale_sartorius import SartoriusScale

    pump = build_pump(PumpConfig(port="COM3"), simulate=False)
    scope = build_oscilloscope(
        OscilloscopeConfig(visa_resource="USB"),
        state=ExperimentState(),
        simulate=False,
    )
    cam = build_camera(CameraConfig(), simulate=False)
    scale = build_scale(ScaleConfig(enabled=True, port="COM5"), simulate=False)
    assert isinstance(pump, MZR7245Pump)
    assert isinstance(scope, KeysightOscilloscope)
    assert isinstance(cam, DigiCamCamera)
    assert isinstance(scale, SartoriusScale)
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/devices/test_factory.py -v`
Expected: ImportError on `build_pump` etc.

- [ ] **Step 3: Extend `devices/__init__.py`**

Replace `src/droplet_lab/devices/__init__.py` with:

```python
"""Hardware device abstractions and factories."""

from droplet_lab.config import (
    CameraConfig,
    OscilloscopeConfig,
    PumpConfig,
    ScaleConfig,
)
from droplet_lab.devices.base import (
    Camera,
    Oscilloscope,
    Pump,
    Scale,
    ScopeMeasurement,
)
from droplet_lab.devices.camera_digicam import DigiCamCamera
from droplet_lab.devices.camera_fake import FakeCamera
from droplet_lab.devices.oscilloscope_fake import FakeOscilloscope
from droplet_lab.devices.oscilloscope_keysight import KeysightOscilloscope
from droplet_lab.devices.pump_fake import FakePump
from droplet_lab.devices.pump_mzr7245 import MZR7245Pump
from droplet_lab.devices.scale_fake import FakeScale
from droplet_lab.devices.scale_sartorius import SartoriusScale
from droplet_lab.state import ExperimentState

__all__ = [
    "Camera",
    "Oscilloscope",
    "Pump",
    "Scale",
    "ScopeMeasurement",
    "build_camera",
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


def build_scale(cfg: ScaleConfig, *, simulate: bool) -> Scale:
    if simulate:
        return FakeScale()
    if cfg.port is None:
        raise ValueError("ScaleConfig.port must be set when simulate=False")
    return SartoriusScale(port=cfg.port, baudrate=cfg.baudrate)
```

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest tests/devices/test_factory.py -v`
Expected: 2 passed.

- [ ] **Step 5: Stage**

```bash
git add src/droplet_lab/devices/__init__.py tests/devices/test_factory.py
```

Suggested commit message: `feat(devices): add build_* factories with simulate switch`

---

## Task 17: PumpWorker thread

**Files:**
- Create: `src/droplet_lab/workers/__init__.py`
- Create: `src/droplet_lab/workers/pump_worker.py`
- Create: `tests/workers/__init__.py`
- Create: `tests/workers/test_pump_worker.py`

- [ ] **Step 1: Write failing tests**

Create `tests/workers/__init__.py` (empty).

Create `tests/workers/test_pump_worker.py`:

```python
import queue
import threading
import time

from droplet_lab.devices.pump_fake import FakePump
from droplet_lab.state import ExperimentState
from droplet_lab.storage import ExperimentDirectory
from droplet_lab.workers.pump_worker import PumpWorker, SetSpeedCommand


def _run_worker(tmp_path, pump, state, *, duration_s=0.4, log_interval_s=0.1):
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    cmd_q: queue.Queue = queue.Queue()
    stop = threading.Event()
    error = threading.Event()
    worker = PumpWorker(
        pump=pump,
        state=state,
        command_queue=cmd_q,
        stop_event=stop,
        error_event=error,
        log_interval_s=log_interval_s,
        experiment_dir=exp,
    )
    t = threading.Thread(target=worker.run)
    t.start()
    try:
        time.sleep(duration_s)
        stop.set()
        t.join(timeout=2.0)
    finally:
        if t.is_alive():
            t.join(timeout=1.0)
    return exp, error


def test_writes_pump_csv_rows(tmp_path) -> None:
    state = ExperimentState()
    state.update(step_index=1, set_speed_rpm=200)
    pump = FakePump()
    with pump:
        exp, error = _run_worker(tmp_path, pump, state, duration_s=0.35, log_interval_s=0.1)
    assert not error.is_set()
    text = (exp.root / "pump.csv").read_text()
    assert "set_speed_rpm" in text
    assert text.count("\n") >= 3  # header + at least 2 rows


def test_consumes_set_speed_command(tmp_path) -> None:
    state = ExperimentState()
    state.update(step_index=1, set_speed_rpm=0)
    pump = FakePump(acceleration_rpm_per_s=10000)
    with pump:
        exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
        cmd_q: queue.Queue = queue.Queue()
        stop = threading.Event()
        error = threading.Event()
        worker = PumpWorker(
            pump=pump,
            state=state,
            command_queue=cmd_q,
            stop_event=stop,
            error_event=error,
            log_interval_s=0.05,
            experiment_dir=exp,
        )
        t = threading.Thread(target=worker.run)
        t.start()
        cmd_q.put(SetSpeedCommand(rpm=350))
        time.sleep(0.3)
        stop.set()
        t.join(timeout=2.0)
    assert pump.get_target_speed_rpm() == 350


def test_sets_error_event_on_pump_failure(tmp_path) -> None:
    class BoomPump(FakePump):
        def get_actual_speed_rpm(self):
            raise RuntimeError("device disconnected")

    pump = BoomPump()
    state = ExperimentState()
    state.update(step_index=1, set_speed_rpm=0)
    with pump:
        exp, error = _run_worker(tmp_path, pump, state, duration_s=0.3)
    assert error.is_set()
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/workers/test_pump_worker.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `pump_worker.py`**

Create `src/droplet_lab/workers/__init__.py`:

```python
"""Background worker threads for long-running device polling."""
```

Create `src/droplet_lab/workers/pump_worker.py`:

```python
"""Pump worker thread.

Continuously logs pump telemetry to ``pump.csv`` and consumes ``SetSpeedCommand``
messages from the orchestrator's queue. Stops cleanly when ``stop_event`` is
set; signals ``error_event`` on hardware failure.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass

from loguru import logger

from droplet_lab.devices.base import Pump
from droplet_lab.state import ExperimentState
from droplet_lab.storage import ExperimentDirectory, PumpRow, utc_now_iso


@dataclass(frozen=True, slots=True)
class SetSpeedCommand:
    rpm: int


class PumpWorker:
    def __init__(
        self,
        *,
        pump: Pump,
        state: ExperimentState,
        command_queue: "queue.Queue[SetSpeedCommand]",
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
        try:
            with self._exp.open_pump_csv() as writer:
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
                        writer.write(
                            PumpRow(
                                timestamp_utc=utc_now_iso(),
                                elapsed_s=round(now - start, 3),
                                step_index=snap.step_index,
                                set_speed_rpm=snap.set_speed_rpm,
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
            try:
                self._pump.stop()
            except Exception:
                self._log.exception("failed to stop pump on shutdown")
            self._log.info("pump worker finished")
```

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest tests/workers/test_pump_worker.py -v`
Expected: 3 passed.

- [ ] **Step 5: Stage**

```bash
git add src/droplet_lab/workers/__init__.py src/droplet_lab/workers/pump_worker.py tests/workers/__init__.py tests/workers/test_pump_worker.py
```

Suggested commit message: `feat(workers): add PumpWorker (telemetry log + speed-set queue)`

---

## Task 18: ScopeWorker thread

**Files:**
- Create: `src/droplet_lab/workers/scope_worker.py`
- Create: `tests/workers/test_scope_worker.py`

- [ ] **Step 1: Write failing tests**

Create `tests/workers/test_scope_worker.py`:

```python
import threading
import time

from droplet_lab.devices.oscilloscope_fake import FakeOscilloscope
from droplet_lab.state import ExperimentState
from droplet_lab.storage import ExperimentDirectory
from droplet_lab.workers.scope_worker import ScopeWorker


def test_writes_oscilloscope_csv(tmp_path) -> None:
    state = ExperimentState()
    state.update(step_index=1, set_speed_rpm=200)
    scope = FakeOscilloscope(state=state)
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    stop = threading.Event()
    error = threading.Event()

    with scope:
        worker = ScopeWorker(
            scope=scope,
            state=state,
            stop_event=stop,
            error_event=error,
            log_interval_s=0.05,
            vibrometer_factor_um_per_v=5280,
            experiment_dir=exp,
        )
        t = threading.Thread(target=worker.run)
        t.start()
        time.sleep(0.3)
        stop.set()
        t.join(timeout=2.0)

    assert not error.is_set()
    text = (exp.root / "oscilloscope.csv").read_text()
    assert "p2p_displacement_um" in text
    assert text.count("\n") >= 3


def test_p2p_displacement_computed_from_vpp(tmp_path) -> None:
    state = ExperimentState()
    state.update(step_index=1, set_speed_rpm=500)
    scope = FakeOscilloscope(state=state, noise_amplitude=0.0)
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    stop = threading.Event()
    error = threading.Event()

    with scope:
        worker = ScopeWorker(
            scope=scope,
            state=state,
            stop_event=stop,
            error_event=error,
            log_interval_s=0.05,
            vibrometer_factor_um_per_v=1000.0,
            experiment_dir=exp,
        )
        t = threading.Thread(target=worker.run)
        t.start()
        time.sleep(0.15)
        stop.set()
        t.join(timeout=2.0)

    rows = (exp.root / "oscilloscope.csv").read_text().strip().splitlines()
    header, *data = [r.split(";") for r in rows]
    vpp_idx = header.index("vpp_v")
    p2p_idx = header.index("p2p_displacement_um")
    for r in data:
        if r[vpp_idx] and r[p2p_idx]:
            assert abs(float(r[p2p_idx]) - float(r[vpp_idx]) * 1000.0) < 1e-6
            return
    raise AssertionError("no row with both vpp and p2p found")
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/workers/test_scope_worker.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `scope_worker.py`**

Create `src/droplet_lab/workers/scope_worker.py`:

```python
"""Oscilloscope worker thread.

Polls the scope at ``log_interval_s`` cadence; tags each row with the current
step from ``ExperimentState``; computes peak-to-peak displacement from Vpp via
the vibrometer factor.
"""

from __future__ import annotations

import threading
import time

from loguru import logger

from droplet_lab.devices.base import Oscilloscope
from droplet_lab.state import ExperimentState
from droplet_lab.storage import ExperimentDirectory, OscilloscopeRow, utc_now_iso


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
        try:
            with self._exp.open_oscilloscope_csv() as writer:
                while not self._stop.is_set():
                    now = time.monotonic()
                    if now >= next_log:
                        snap = self._state.snapshot()
                        m = self._scope.measure()
                        p2p = m.vpp_v * self._factor if m.vpp_v is not None else None
                        writer.write(
                            OscilloscopeRow(
                                timestamp_utc=utc_now_iso(),
                                elapsed_s=round(now - start, 3),
                                step_index=snap.step_index,
                                set_speed_rpm=snap.set_speed_rpm,
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
            self._log.info("scope worker finished")
```

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest tests/workers/test_scope_worker.py -v`
Expected: 2 passed.

- [ ] **Step 5: Stage**

```bash
git add src/droplet_lab/workers/scope_worker.py tests/workers/test_scope_worker.py
```

Suggested commit message: `feat(workers): add ScopeWorker (measure + tag + p2p calc)`

---

## Task 19: ScaleWorker thread

**Files:**
- Create: `src/droplet_lab/workers/scale_worker.py`
- Create: `tests/workers/test_scale_worker.py`

- [ ] **Step 1: Write failing tests**

Create `tests/workers/test_scale_worker.py`:

```python
import threading
import time

from droplet_lab.devices.scale_fake import FakeScale
from droplet_lab.state import ExperimentState
from droplet_lab.storage import ExperimentDirectory
from droplet_lab.workers.scale_worker import ScaleWorker


def test_writes_scale_csv(tmp_path) -> None:
    state = ExperimentState()
    state.update(step_index=1, set_speed_rpm=200)
    scale = FakeScale()
    exp = ExperimentDirectory.create(base_dir=tmp_path, experiment_id="X")
    stop = threading.Event()
    error = threading.Event()
    with scale:
        worker = ScaleWorker(
            scale=scale,
            state=state,
            stop_event=stop,
            error_event=error,
            log_interval_s=0.05,
            experiment_dir=exp,
        )
        t = threading.Thread(target=worker.run)
        t.start()
        time.sleep(0.2)
        stop.set()
        t.join(timeout=2.0)
    assert not error.is_set()
    text = (exp.root / "scale.csv").read_text()
    assert "weight_g" in text
    assert text.count("\n") >= 3
```

- [ ] **Step 2: Verify the test fails**

Run: `uv run pytest tests/workers/test_scale_worker.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `scale_worker.py`**

Create `src/droplet_lab/workers/scale_worker.py`:

```python
"""Scale worker thread (optional — only spawned if the scale is enabled)."""

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
            with self._exp.open_scale_csv() as writer:
                while not self._stop.is_set():
                    now = time.monotonic()
                    if now >= next_log:
                        snap = self._state.snapshot()
                        writer.write(
                            ScaleRow(
                                timestamp_utc=utc_now_iso(),
                                elapsed_s=round(now - start, 3),
                                step_index=snap.step_index,
                                set_speed_rpm=snap.set_speed_rpm,
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

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest tests/workers/test_scale_worker.py -v`
Expected: 1 passed.

- [ ] **Step 5: Stage**

```bash
git add src/droplet_lab/workers/scale_worker.py tests/workers/test_scale_worker.py
```

Suggested commit message: `feat(workers): add ScaleWorker (optional)`

---

## Task 20: CameraWorker (per-step capture loop with watchdog)

**Files:**
- Create: `src/droplet_lab/workers/camera_worker.py`
- Create: `tests/workers/test_camera_worker.py`

- [ ] **Step 1: Write failing tests**

Create `tests/workers/test_camera_worker.py`:

```python
import threading
from pathlib import Path

import pytest

from droplet_lab.devices.camera_fake import FakeCamera
from droplet_lab.workers.camera_worker import (
    CameraResult,
    CameraResultStatus,
    run_camera_capture,
)


def test_completes_when_duration_elapses(tmp_path: Path) -> None:
    cam = FakeCamera()
    with cam:
        result = run_camera_capture(
            camera=cam,
            output_folder=tmp_path,
            interval_s=0.05,
            duration_s=0.2,
            latency_tolerance_s=0.05,
            stop_event=threading.Event(),
        )
    assert result.status is CameraResultStatus.COMPLETED
    assert result.captures >= 4
    assert len(list(tmp_path.glob("*.NEF"))) == result.captures


def test_aborts_on_stop_event(tmp_path: Path) -> None:
    cam = FakeCamera()
    stop = threading.Event()

    def trip() -> None:
        import time
        time.sleep(0.1)
        stop.set()

    threading.Thread(target=trip).start()
    with cam:
        result = run_camera_capture(
            camera=cam,
            output_folder=tmp_path,
            interval_s=0.05,
            duration_s=10.0,  # would normally run forever
            latency_tolerance_s=0.05,
            stop_event=stop,
        )
    assert result.status is CameraResultStatus.ABORTED


def test_marks_failed_when_capture_raises(tmp_path: Path) -> None:
    cam = FakeCamera(fail_after_triggers=2)
    with cam:
        result = run_camera_capture(
            camera=cam,
            output_folder=tmp_path,
            interval_s=0.05,
            duration_s=0.5,
            latency_tolerance_s=0.05,
            stop_event=threading.Event(),
        )
    assert result.status is CameraResultStatus.FAILED
    assert result.error is not None


def test_zero_duration_returns_no_imaging(tmp_path: Path) -> None:
    cam = FakeCamera()
    with cam:
        result = run_camera_capture(
            camera=cam,
            output_folder=tmp_path,
            interval_s=0.05,
            duration_s=0.0,
            latency_tolerance_s=0.05,
            stop_event=threading.Event(),
        )
    assert result.status is CameraResultStatus.NO_IMAGING
    assert result.captures == 0
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/workers/test_camera_worker.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `camera_worker.py`**

Create `src/droplet_lab/workers/camera_worker.py`:

```python
"""Per-step camera capture loop.

Synchronous (called from the orchestrator), but checks ``stop_event`` between
captures so a Ctrl-C interrupts cleanly. Returns a ``CameraResult``; the
orchestrator interprets the status and writes step.json accordingly.

The function intentionally does not raise on capture errors — failures become
``CameraResultStatus.FAILED`` with the exception attached, so the orchestrator
can decide whether to abort the experiment.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from loguru import logger

from droplet_lab.devices.base import Camera


class CameraResultStatus(StrEnum):
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"
    NO_IMAGING = "no_imaging"


@dataclass(frozen=True, slots=True)
class CameraResult:
    status: CameraResultStatus
    captures: int
    error: str | None = None


def run_camera_capture(
    *,
    camera: Camera,
    output_folder: Path,
    interval_s: float,
    duration_s: float,
    latency_tolerance_s: float,
    stop_event: threading.Event,
) -> CameraResult:
    log = logger.bind(component="camera")

    if duration_s <= 0:
        log.info("step has zero imaging duration, skipping capture")
        return CameraResult(status=CameraResultStatus.NO_IMAGING, captures=0)

    try:
        camera.set_output_folder(output_folder)
    except Exception as e:
        log.exception("failed to set output folder")
        return CameraResult(status=CameraResultStatus.FAILED, captures=0, error=str(e))

    start = time.monotonic()
    next_capture_at = start
    captures = 0

    while True:
        now = time.monotonic()
        elapsed = now - start
        if elapsed > duration_s:
            break
        if stop_event.is_set():
            log.info("stop signal received during capture")
            return CameraResult(status=CameraResultStatus.ABORTED, captures=captures)
        if now >= next_capture_at:
            try:
                camera.trigger_capture()
            except Exception as e:
                log.exception("capture failed at frame {}", captures + 1)
                return CameraResult(
                    status=CameraResultStatus.FAILED,
                    captures=captures,
                    error=str(e),
                )
            captures += 1
            log.info("captured frame {}", captures)
            next_capture_at += interval_s
        else:
            time.sleep(0.02)

    if latency_tolerance_s > 0:
        log.debug("waiting {} s latency tolerance", latency_tolerance_s)
        # Cooperative wait
        deadline = time.monotonic() + latency_tolerance_s
        while time.monotonic() < deadline:
            if stop_event.is_set():
                return CameraResult(status=CameraResultStatus.ABORTED, captures=captures)
            time.sleep(0.02)

    return CameraResult(status=CameraResultStatus.COMPLETED, captures=captures)
```

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest tests/workers/test_camera_worker.py -v`
Expected: 4 passed.

- [ ] **Step 5: Stage**

```bash
git add src/droplet_lab/workers/camera_worker.py tests/workers/test_camera_worker.py
```

Suggested commit message: `feat(workers): add CameraWorker (per-step capture loop)`

---

## Task 21: Orchestrator (`orchestrator.py`)

**Files:**
- Create: `src/droplet_lab/orchestrator.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/conftest.py`
- Create: `tests/integration/test_orchestrator_end_to_end.py`

- [ ] **Step 1: Write failing tests**

Create `tests/integration/__init__.py` (empty).

Create `tests/integration/conftest.py`:

```python
from pathlib import Path

import pytest

from droplet_lab.config import (
    ActuationConfig,
    CameraConfig,
    DevicesConfig,
    ExperimentConfig,
    LimitsConfig,
    OscilloscopeConfig,
    OutputConfig,
    PumpConfig,
    RampStep,
    ScaleConfig,
    TimingConfig,
)


@pytest.fixture
def minimal_config(tmp_path: Path) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="INT_TEST",
        nozzle_id="1mm_A",
        actuation=ActuationConfig(
            frequency_hz=200,
            voltage_v=5,
            vibrometer_factor_um_per_v=5280,
        ),
        ramp=[
            RampStep(speed_rpm=200, hold_s=0.4),
            RampStep(speed_rpm=300, hold_s=0.4),
        ],
        timing=TimingConfig(
            stabilization_s=0.1,
            image_interval_s=0.1,
            camera_latency_tolerance_s=0.05,
        ),
        limits=LimitsConfig(max_speed_rpm=1000),
        devices=DevicesConfig(
            pump=PumpConfig(port="COM3"),
            oscilloscope=OscilloscopeConfig(visa_resource="USB"),
            camera=CameraConfig(),
            scale=ScaleConfig(enabled=False),
        ),
        output=OutputConfig(base_dir=tmp_path),
    )
```

Create `tests/integration/test_orchestrator_end_to_end.py`:

```python
import json
import threading
import time
from pathlib import Path

from droplet_lab.config import ExperimentConfig
from droplet_lab.devices.camera_fake import FakeCamera
from droplet_lab.devices.oscilloscope_fake import FakeOscilloscope
from droplet_lab.devices.pump_fake import FakePump
from droplet_lab.devices.scale_fake import FakeScale
from droplet_lab.orchestrator import Orchestrator, OrchestratorResult
from droplet_lab.state import ExperimentState, ExperimentStatus, StepStatus


def _build_devices(state: ExperimentState, *, camera: FakeCamera | None = None) -> dict:
    return {
        "pump": FakePump(acceleration_rpm_per_s=10000),
        "scope": FakeOscilloscope(state=state),
        "camera": camera if camera is not None else FakeCamera(),
        "scale": FakeScale(),
    }


def _run(config: ExperimentConfig, devices: dict, *, stop_after_s: float | None = None) -> OrchestratorResult:
    state = ExperimentState()
    orch = Orchestrator(config=config, devices=devices, state=state)
    if stop_after_s is not None:
        def trip() -> None:
            time.sleep(stop_after_s)
            orch.request_stop()
        threading.Thread(target=trip).start()
    return orch.run()


def test_full_ramp_completes(minimal_config: ExperimentConfig) -> None:
    state = ExperimentState()
    devices = _build_devices(state)
    result = Orchestrator(config=minimal_config, devices=devices, state=state).run()

    assert result.status is ExperimentStatus.COMPLETED
    exp = result.experiment_dir.root
    assert (exp / "experiment.json").exists()
    assert (exp / "pump.csv").exists()
    assert (exp / "oscilloscope.csv").exists()
    assert not (exp / "scale.csv").exists()  # scale disabled

    steps = sorted((exp / "steps").iterdir())
    assert len(steps) == 2
    for step in steps:
        meta = json.loads((step / "step.json").read_text())
        assert meta["status"] in {StepStatus.COMPLETED.value, StepStatus.COMPLETED_NO_IMAGING.value}
        assert (step / "images").exists()


def test_ctrl_c_aborts_cleanly(minimal_config: ExperimentConfig) -> None:
    state = ExperimentState()
    devices = _build_devices(state)
    result = _run(minimal_config, devices, stop_after_s=0.2)
    assert result.status is ExperimentStatus.ABORTED


def test_camera_failure_marks_experiment_failed(minimal_config: ExperimentConfig) -> None:
    state = ExperimentState()
    cam = FakeCamera(fail_after_triggers=1)
    devices = _build_devices(state, camera=cam)
    result = Orchestrator(config=minimal_config, devices=devices, state=state).run()

    assert result.status is ExperimentStatus.FAILED
    steps = sorted((result.experiment_dir.root / "steps").iterdir())
    failed = [s for s in steps if json.loads((s / "step.json").read_text())["status"] == StepStatus.CAMERA_FAILED.value]
    assert len(failed) >= 1


def test_scale_enabled_writes_scale_csv(minimal_config: ExperimentConfig) -> None:
    cfg = minimal_config.model_copy(
        update={
            "devices": minimal_config.devices.model_copy(
                update={"scale": minimal_config.devices.scale.model_copy(update={"enabled": True, "port": "COM5"})}
            )
        }
    )
    state = ExperimentState()
    devices = _build_devices(state)
    result = Orchestrator(config=cfg, devices=devices, state=state).run()
    assert (result.experiment_dir.root / "scale.csv").exists()
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/integration/test_orchestrator_end_to_end.py -v`
Expected: ImportError on `Orchestrator`.

- [ ] **Step 3: Implement `orchestrator.py`**

Create `src/droplet_lab/orchestrator.py`:

```python
"""Experiment orchestrator.

Owns the lifecycle of one experiment run:

* Build the ``ExperimentDirectory``, persist ``experiment.json``.
* Spawn ``PumpWorker`` / ``ScopeWorker`` (and optional ``ScaleWorker``) threads.
* Walk the ramp profile, signalling speed changes and per-step camera capture.
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
from typing import TypedDict

from loguru import logger

from droplet_lab.config import ExperimentConfig
from droplet_lab.devices.base import Camera, Oscilloscope, Pump, Scale
from droplet_lab.logging_setup import setup_logging
from droplet_lab.state import (
    CameraStatus,
    ExperimentState,
    ExperimentStatus,
    StepStatus,
)
from droplet_lab.storage import ExperimentDirectory, utc_now_iso
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
    scale: Scale


@dataclass(frozen=True, slots=True)
class OrchestratorResult:
    status: ExperimentStatus
    experiment_dir: ExperimentDirectory
    failure_reason: str | None = None


_PUMP_LOG_INTERVAL_S = 5.0
_SCOPE_LOG_INTERVAL_S = 15.0
_SCALE_LOG_INTERVAL_S = 1.0


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
                stack.enter_context(self._devices["camera"])
                scale_cm = (
                    stack.enter_context(self._devices["scale"])
                    if self._cfg.devices.scale.enabled
                    else None
                )

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
                    vibrometer_factor_um_per_v=self._cfg.actuation.vibrometer_factor_um_per_v,
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
                        log_interval_s=_SCALE_LOG_INTERVAL_S,
                        experiment_dir=exp,
                    )
                    scale_thread = threading.Thread(target=scale_worker.run, name="scale")
                    scale_thread.start()

                result_status, failure_reason = self._walk_ramp(
                    exp=exp,
                    cmd_q=cmd_q,
                    camera=self._devices["camera"],
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

    def _walk_ramp(
        self,
        *,
        exp: ExperimentDirectory,
        cmd_q: queue.Queue[SetSpeedCommand],
        camera: Camera,
    ) -> tuple[ExperimentStatus, str | None]:
        # Initial speed via cmd_q so PumpWorker logs it
        first = self._cfg.ramp[0]
        cmd_q.put(SetSpeedCommand(rpm=first.speed_rpm))

        for step_index, step in enumerate(self._cfg.ramp, start=1):
            if self._stop.is_set() or self._error.is_set():
                return self._final_status_after_break(), None

            self._state.update(step_index=step_index, set_speed_rpm=step.speed_rpm)

            if step_index > 1:
                cmd_q.put(SetSpeedCommand(rpm=step.speed_rpm))

            step_folder = exp.create_step_folder(
                step_index=step_index,
                set_speed_rpm=step.speed_rpm,
            )
            step_meta = self._initial_step_meta(step_index, step.speed_rpm, step.hold_s)
            self._write_step_json(step_folder, step_meta)

            self._log.info("step {} @ {} rpm — stabilizing", step_index, step.speed_rpm)
            step_meta["status"] = StepStatus.STABILIZING.value
            self._write_step_json(step_folder, step_meta)

            if self._wait(self._cfg.timing.stabilization_s):
                step_meta["status"] = StepStatus.ABORTED.value
                step_meta["end_time_utc"] = utc_now_iso()
                self._write_step_json(step_folder, step_meta)
                return self._final_status_after_break(), None

            imaging_duration = max(0.0, step.hold_s - self._cfg.timing.stabilization_s)
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
                case CameraResultStatus.NO_IMAGING:
                    step_meta["status"] = StepStatus.COMPLETED_NO_IMAGING.value
                    step_meta["camera_status"] = CameraStatus.NOT_STARTED.value
                case CameraResultStatus.ABORTED:
                    step_meta["status"] = StepStatus.ABORTED.value
                    step_meta["camera_status"] = CameraStatus.ABORTED.value
                    self._write_step_json(step_folder, step_meta)
                    return self._final_status_after_break(), None
                case CameraResultStatus.FAILED:
                    step_meta["status"] = StepStatus.CAMERA_FAILED.value
                    step_meta["camera_status"] = CameraStatus.FAILED.value
                    step_meta["camera_error"] = result.error
                    self._write_step_json(step_folder, step_meta)
                    return ExperimentStatus.FAILED, f"camera failed at step {step_index}"

            self._write_step_json(step_folder, step_meta)

        return ExperimentStatus.COMPLETED, None

    def _wait(self, seconds: float) -> bool:
        """Cooperative wait. Returns True if stop_event/error_event tripped."""
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

    def _initial_step_meta(self, step_index: int, rpm: int, hold_s: float) -> dict:
        return {
            "step_index": step_index,
            "set_speed_rpm": rpm,
            "hold_s": hold_s,
            "stabilization_s": self._cfg.timing.stabilization_s,
            "image_interval_s": self._cfg.timing.image_interval_s,
            "camera_latency_tolerance_s": self._cfg.timing.camera_latency_tolerance_s,
            "start_time_utc": utc_now_iso(),
            "status": StepStatus.PLANNED.value,
            "camera_status": CameraStatus.NOT_STARTED.value,
            "captures": 0,
        }

    def _write_step_json(self, folder: Path, payload: dict) -> None:
        ExperimentDirectory.write_json(folder / "step.json", payload)

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
        payload["written_at_utc"] = utc_now_iso()
        ExperimentDirectory.write_json(exp.root / "experiment.json", payload)
```

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest tests/integration/test_orchestrator_end_to_end.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -v`
Expected: all green.

Run: `uv run mypy src tests`
Expected: `Success`.

- [ ] **Step 6: Stage**

```bash
git add src/droplet_lab/orchestrator.py tests/integration/__init__.py tests/integration/conftest.py tests/integration/test_orchestrator_end_to_end.py
```

Suggested commit message: `feat(orchestrator): walk ramp, manage workers, write experiment/step JSON`

---

## Task 22: CLI (`cli.py`) with typer

**Files:**
- Create: `src/droplet_lab/cli.py`
- Create: `tests/cli/__init__.py`
- Create: `tests/cli/test_cli.py`

- [ ] **Step 1: Write failing tests**

Create `tests/cli/__init__.py` (empty).

Create `tests/cli/test_cli.py`:

```python
from pathlib import Path

import yaml
from typer.testing import CliRunner

from droplet_lab.cli import app

runner = CliRunner()


def _example_yaml(tmp_path: Path) -> Path:
    data = {
        "experiment_id": "CLI_TEST",
        "nozzle_id": "1mm_A",
        "actuation": {"frequency_hz": 200, "voltage_v": 5, "vibrometer_factor_um_per_v": 5280},
        "ramp": [{"speed_rpm": 200, "hold_s": 0.3}],
        "timing": {"stabilization_s": 0.05, "image_interval_s": 0.1, "camera_latency_tolerance_s": 0.05},
        "limits": {"max_speed_rpm": 1000},
        "devices": {
            "pump": {"port": "COM3"},
            "oscilloscope": {"visa_resource": "USB"},
            "camera": {},
            "scale": {"enabled": False},
        },
        "output": {"base_dir": str(tmp_path)},
    }
    p = tmp_path / "exp.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


def test_validate_ok(tmp_path: Path) -> None:
    yml = _example_yaml(tmp_path)
    res = runner.invoke(app, ["validate", str(yml)])
    assert res.exit_code == 0, res.output
    assert "OK" in res.output


def test_validate_rejects_bad_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("experiment_id: TEST\n")  # missing required fields
    res = runner.invoke(app, ["validate", str(bad)])
    assert res.exit_code != 0


def test_dry_run_prints_plan(tmp_path: Path) -> None:
    yml = _example_yaml(tmp_path)
    res = runner.invoke(app, ["run", str(yml), "--dry-run", "--no-confirm", "--simulate"])
    assert res.exit_code == 0, res.output
    assert "200" in res.output


def test_run_simulate_completes(tmp_path: Path) -> None:
    yml = _example_yaml(tmp_path)
    res = runner.invoke(app, ["run", str(yml), "--simulate", "--no-confirm", "--no-tui"])
    assert res.exit_code == 0, res.output
    runs = list(tmp_path.iterdir())
    # at least the YAML and one experiment folder exist
    assert any(p.name != "exp.yaml" for p in runs)


def test_simulate_only_accepts_csv(tmp_path: Path) -> None:
    yml = _example_yaml(tmp_path)
    res = runner.invoke(
        app,
        ["run", str(yml), "--simulate-only", "pump,scope,camera,scale", "--no-confirm", "--no-tui"],
    )
    assert res.exit_code == 0, res.output


def test_simulate_only_rejects_unknown_device(tmp_path: Path) -> None:
    yml = _example_yaml(tmp_path)
    res = runner.invoke(
        app,
        ["run", str(yml), "--simulate-only", "foo", "--no-confirm", "--no-tui"],
    )
    assert res.exit_code != 0
    assert "unknown device" in res.output or "foo" in res.output


def test_new_command_creates_yaml(tmp_path: Path) -> None:
    target = tmp_path / "experiments" / "demo.yaml"
    res = runner.invoke(app, ["new", str(target)])
    assert res.exit_code == 0, res.output
    assert target.exists()
    # The scaffolded file must validate
    from droplet_lab.config import load_experiment
    cfg = load_experiment(target)
    assert cfg.experiment_id


def test_version() -> None:
    res = runner.invoke(app, ["--version"])
    assert res.exit_code == 0
    assert "droplet" in res.output.lower() or "0." in res.output
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/cli/test_cli.py -v`
Expected: ImportError on `app`.

- [ ] **Step 3: Implement `cli.py`**

Create `src/droplet_lab/cli.py`:

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
    ActuationConfig,
    CameraConfig,
    DevicesConfig,
    ExperimentConfig,
    LimitsConfig,
    OscilloscopeConfig,
    OutputConfig,
    PumpConfig,
    RampStep,
    ScaleConfig,
    TimingConfig,
    load_experiment,
)
from droplet_lab.devices import (
    build_camera,
    build_oscilloscope,
    build_pump,
    build_scale,
)
from droplet_lab.orchestrator import DeviceBundle, Orchestrator
from droplet_lab.state import ExperimentState, ExperimentStatus

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"droplet {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version and exit"),
    ] = False,
) -> None:
    """Droplet Lab controller."""


@app.command()
def validate(yaml_path: Path) -> None:
    """Validate an experiment YAML without opening any hardware."""
    cfg = load_experiment(yaml_path)
    typer.echo(f"OK: {cfg.experiment_id} ({len(cfg.ramp)} steps)")


_VALID_SIMULATE_ONLY = {"pump", "scope", "camera", "scale"}


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
    simulate: Annotated[bool, typer.Option("--simulate", help="Use FakePump/FakeScope/FakeCamera/FakeScale")] = False,
    simulate_only: Annotated[
        str | None,
        typer.Option(
            "--simulate-only",
            help="Comma-separated list of devices to mock (pump,scope,camera,scale)",
        ),
    ] = None,
    output_dir: Annotated[Path | None, typer.Option(help="Override output.base_dir")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print the plan and exit")] = False,
    no_confirm: Annotated[bool, typer.Option("--no-confirm", help="Skip 'press Enter to start'")] = False,
    no_tui: Annotated[bool, typer.Option("--no-tui", help="Disable rich live display")] = False,
) -> None:
    """Run an experiment."""
    cfg = load_experiment(yaml_path)
    if output_dir is not None:
        cfg = cfg.model_copy(update={"output": OutputConfig(base_dir=output_dir)})

    fakes = _parse_simulate_only(simulate_only)
    if simulate:
        fakes = set(_VALID_SIMULATE_ONLY)

    typer.echo(f"Experiment: {cfg.experiment_id}  nozzle={cfg.nozzle_id}")
    if fakes:
        typer.echo(f"Simulated devices: {sorted(fakes)}")
    for i, step in enumerate(cfg.ramp, start=1):
        typer.echo(f"  step {i:02d}: {step.speed_rpm} rpm for {step.hold_s} s")

    if dry_run:
        typer.echo("--dry-run: not executing")
        return

    if not no_confirm:
        typer.confirm("Start experiment now?", abort=True)

    state = ExperimentState()
    devices: DeviceBundle = {
        "pump": build_pump(cfg.devices.pump, simulate="pump" in fakes),
        "scope": build_oscilloscope(cfg.devices.oscilloscope, state=state, simulate="scope" in fakes),
        "camera": build_camera(cfg.devices.camera, simulate="camera" in fakes),
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
        actuation=ActuationConfig(frequency_hz=200, voltage_v=5, vibrometer_factor_um_per_v=5280),
        ramp=[RampStep(speed_rpm=200, hold_s=30), RampStep(speed_rpm=300, hold_s=60)],
        timing=TimingConfig(stabilization_s=10, image_interval_s=5, camera_latency_tolerance_s=1.0),
        limits=LimitsConfig(max_speed_rpm=1000),
        devices=DevicesConfig(
            pump=PumpConfig(port="COM3"),
            oscilloscope=OscilloscopeConfig(visa_resource="USB0::0xXXXX::INSTR"),
            camera=CameraConfig(),
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
    except Exception as e:  # noqa: BLE001
        typer.echo(f"  (error: {e})")

    typer.echo("VISA resources:")
    try:
        import pyvisa
        rm = pyvisa.ResourceManager()
        for r in rm.list_resources():
            typer.echo(f"  {r}")
        rm.close()
    except Exception as e:  # noqa: BLE001
        typer.echo(f"  (error: {e})")
```

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest tests/cli/test_cli.py -v`
Expected: 6 passed.

- [ ] **Step 5: Verify CLI works as a script**

Run: `uv run droplet --version`
Expected: prints `droplet 0.1.0`.

Run: `uv run droplet validate experiments/example_hpmc.yaml`
Expected: `OK: HPMC_Test_01 (5 steps)`.

- [ ] **Step 6: Stage**

```bash
git add src/droplet_lab/cli.py tests/cli/__init__.py tests/cli/test_cli.py
```

Suggested commit message: `feat(cli): add typer app (run, validate, new, list-devices)`

---

## Task 23: Experiments README

**Files:**
- Create: `experiments/README.md`

- [ ] **Step 1: Write `experiments/README.md`**

Create `experiments/README.md`:

````markdown
# Experiments

Each experiment is one YAML file. Run it with:

```bash
uv run droplet run experiments/<your_file>.yaml
```

## Field reference

| Field | Type | Unit | Description |
|---|---|---|---|
| `experiment_id` | string | — | Free-form identifier; appears in output folder name. |
| `nozzle_id` | string | — | Free-form nozzle identifier. |
| `actuation.frequency_hz` | float > 0 | Hz | Driving frequency the actuator is set to. |
| `actuation.voltage_v` | float > 0 | V | Driving voltage. |
| `actuation.vibrometer_factor_um_per_v` | float > 0 | µm/V | Calibration factor; multiplied by Vpp on CH1 to get peak-to-peak displacement. |
| `ramp[i].speed_rpm` | int > 0 | rpm | Pump speed for this step. |
| `ramp[i].hold_s` | float > 0 | s | Total time spent at this speed. Imaging duration = `hold_s - timing.stabilization_s`. |
| `timing.stabilization_s` | float ≥ 0 | s | Wait time after speed change before imaging starts. |
| `timing.image_interval_s` | float > 0 | s | Time between camera triggers. |
| `timing.camera_latency_tolerance_s` | float ≥ 0 | s | Extra wait after the planned imaging window before declaring the camera done. |
| `limits.max_speed_rpm` | int > 0 | rpm | Hard cap; ramp validation rejects steps exceeding this. |
| `devices.pump.port` | string | — | COM port (Windows) or `/dev/tty…` (Linux/macOS). |
| `devices.pump.baudrate` | int > 0 | baud | Default `9600`. |
| `devices.oscilloscope.visa_resource` | string | — | VISA resource string from `droplet list-devices`. |
| `devices.oscilloscope.timeout_ms` | int > 0 | ms | SCPI query timeout. |
| `devices.camera.digicam_url` | string | — | DigiCamControl HTTP server URL (default `http://localhost:5513`). |
| `devices.camera.request_timeout_s` | float > 0 | s | HTTP request timeout. |
| `devices.scale.enabled` | bool | — | If `false`, scale is not opened and `scale.csv` is not written. |
| `devices.scale.port` | string\|null | — | Required when `enabled: true`. |
| `devices.scale.baudrate` | int > 0 | baud | Default `9600`. |
| `output.base_dir` | path | — | Parent directory for run outputs. The actual run folder is `<UTC-timestamp>__<experiment_id>` inside it. |

## Tips

* Run `uv run droplet validate <yaml>` after editing to catch typos and missing fields.
* Use `--simulate` for a dry-run with fake hardware:
  ```bash
  uv run droplet run experiments/example_hpmc.yaml --simulate
  ```
* The shipped `example_hpmc.yaml` is a working reference — copy and edit it for your runs.
````

- [ ] **Step 2: Stage**

```bash
git add experiments/README.md
```

Suggested commit message: `docs(experiments): add YAML field reference`

---

## Task 24: Project README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the README**

Create `README.md` (overwriting any existing one):

````markdown
# Droplet Lab Controller

Single-process Python controller for a droplet-generation lab setup. One YAML
file per experiment drives the gear pump, oscilloscope, DSLR camera (via
DigiCamControl) and (optionally) the lab balance.

## What this is

* You write one YAML file describing the experiment (ramp profile, actuation,
  device addresses).
* `droplet run` drives the hardware, writes structured outputs (CSV per device,
  JSON metadata, raw images per step), and stops cleanly on `Ctrl-C`.
* Every device has a fake counterpart, so you can run a complete experiment
  without any hardware attached (`--simulate`).

## Hardware overview

| Device | Model | Connection | Required external software |
|---|---|---|---|
| Pump | Ismatec MZR-7245 | RS-232 (COM port, 9600 8N1) | — |
| Oscilloscope | Keysight DSOX-series | USB (VISA) | NI-VISA runtime |
| Camera | Nikon DSLR | USB → DigiCamControl HTTP server | DigiCamControl with HTTP server enabled (port 5513) |
| Scale (optional) | Sartorius balance | RS-232 (COM port, 9600 7E1) | — |

## One-time setup

### 1. Install `uv`

```powershell
# Windows (PowerShell)
winget install astral-sh.uv
```

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Clone and sync

```bash
git clone <repo-url>
cd droplet-generation-setup-controller
uv sync --all-extras
```

This installs Python 3.12 (if not already present) and all dependencies into a
local `.venv/`.

### 3. Verify

```bash
uv run droplet --version
```

### 4. Lab-PC-only steps

* Install [NI-VISA runtime](https://www.ni.com/en/support/downloads/drivers/download.ni-visa.html).
* Install [DigiCamControl](https://digicamcontrol.com/) and enable the HTTP server (default port 5513).
* Identify which COM port your pump and balance are on:

  ```bash
  uv run droplet list-devices
  ```

## Quick start — your first experiment

### 1. Scaffold

```bash
uv run droplet new experiments/my_first_test.yaml
```

### 2. Edit

Open `experiments/my_first_test.yaml`. Adjust at minimum:

* `experiment_id` (will appear in the output folder name)
* `ramp` (list of `{ speed_rpm, hold_s }` pairs)
* `devices.pump.port` and `devices.oscilloscope.visa_resource` (use the values
  from `droplet list-devices`)
* `output.base_dir` (where outputs are written)

See [`experiments/README.md`](experiments/README.md) for the full field reference.

### 3. Validate

```bash
uv run droplet validate experiments/my_first_test.yaml
```

Catches typos, missing fields, out-of-range values — without touching hardware.

### 4. Dry-run on your laptop

```bash
uv run droplet run experiments/my_first_test.yaml --simulate --no-confirm
```

Runs the entire experiment with simulated hardware. Produces the same output
structure (CSVs, JSON, placeholder image files), so you can verify your
pipeline before going to the lab.

### 5. Real run

On the lab PC, with hardware connected:

```bash
uv run droplet run experiments/my_first_test.yaml
```

You'll be asked to press Enter to confirm, then the ramp executes. Press
`Ctrl-C` at any point for a graceful shutdown (writes a final
`status: aborted`); a second `Ctrl-C` within two seconds force-quits.

## Output

Each run creates one folder:

```
<base_dir>/<UTC-timestamp>__<experiment_id>/
├── experiment.json         # full config + final status + reason (if failed)
├── experiment.log          # complete log of the run (all threads)
├── pump.csv                # set/actual rpm + temperature, every 5 s
├── oscilloscope.csv        # frequency, Vpp, displacement, channel RMS, every 15 s
├── scale.csv               # only when scale.enabled = true
└── steps/
    ├── step_01_200rpm/
    │   ├── step.json       # step metadata, final status, capture count
    │   └── images/         # raw camera output for this step
    ├── step_02_250rpm/
    └── ...
```

Read CSVs with pandas:

```python
import pandas as pd
df = pd.read_csv("pump.csv", sep=";", parse_dates=["timestamp_utc"])
```

All timestamps are UTC ISO 8601 with microsecond precision.

## Common workflows

**Run with selective fakes** (e.g. test the pump real, mock the camera):

```bash
uv run droplet run experiments/foo.yaml --simulate-only camera,scale
```

Devices not listed run against real hardware. Use bare `--simulate` to mock all four.

**Inspect the log of a finished run:**

```bash
cat <base_dir>/<run-folder>/experiment.log
```

**See where data is going during a run:**

The first line of stdout is `experiment dir: ...`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `uv: command not found` | uv not in PATH | Reopen the shell after install, or use the absolute path. |
| `serial.SerialException: could not open port 'COM3'` | Port held by another process / wrong number / driver missing | Close DigiCamControl/IDE serial monitors; use `droplet list-devices` to confirm. |
| `pyvisa.errors.VisaIOError: VI_ERROR_RSRC_NFOUND` | VISA resource string wrong, scope off, or NI-VISA not installed | Run `droplet list-devices` to find the actual resource string. |
| `requests.exceptions.ConnectionError` to `:5513` | DigiCamControl HTTP server not running | Open DigiCamControl, enable web server in settings. |
| `PermissionError` on output folder | Network share not mounted, or insufficient rights | Mount `W:`; verify with `Test-Path` (Windows) / `ls` (Unix). |
| Validation error mentions `extra_forbidden` | Typo in YAML field name | Diff against `experiments/example_hpmc.yaml`. |
| Camera triggers but no images appear in `images/` | DigiCamControl saves to its own folder | The orchestrator sets `session.folder` per step — confirm in DigiCamControl that "Use original filename" is on and "Download images" is enabled. |

## Developer guide

### Repo structure

```
src/droplet_lab/
    cli.py              entry-point (typer)
    config.py           pydantic v2 models
    state.py            StrEnums + thread-safe ExperimentState
    storage.py          ExperimentDirectory, CSV writers
    logging_setup.py    loguru sinks
    orchestrator.py     ramp loop + thread coordination
    devices/            Protocols + Real* + Fake* per device
    workers/            background threads (pump, scope, scale, camera)
tests/
    unit/               isolated logic tests
    devices/            fakes + mocked real devices
    workers/            thread tests with fakes
    integration/        end-to-end orchestrator runs
    cli/                typer CliRunner tests
experiments/            YAML configs + field reference README
```

### Run tests, lint, type-check

```bash
uv run pytest                                       # all tests
uv run pytest tests/integration -v                  # just E2E
uv run pytest --cov=droplet_lab --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
```

### Pre-commit

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

### Adding a new device

1. **Define the protocol** in `src/droplet_lab/devices/base.py` (or extend an
   existing one).
2. **Implement** `src/droplet_lab/devices/<name>_<vendor>.py` (real driver) and
   `src/droplet_lab/devices/<name>_fake.py` (deterministic in-memory simulator).
3. **Wire into the factory** in `src/droplet_lab/devices/__init__.py`.
4. **Add a worker thread** in `src/droplet_lab/workers/` if it produces a
   continuous stream; otherwise drive it directly from the orchestrator.
5. **Tests**: protocol satisfaction (structural typing), determinism of the
   fake, mocked real driver, and an end-to-end test if it touches CSV output.

### Threading model

* One main thread (orchestrator).
* One thread per long-running device worker (`pump`, `scope`, optional
  `scale`).
* Per-step camera capture runs synchronously in the orchestrator thread.
* Coordination: `queue.Queue` for commands, `threading.Event` for
  stop/error signalling, a thread-safe `ExperimentState` for shared
  step + speed state.

There is no async — `pyvisa` and `pyserial` are blocking, threads are the right
fit.
````

- [ ] **Step 2: Stage**

```bash
git add README.md
```

Suggested commit message: `docs: rewrite README for new package layout`

---

## Task 25: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Replace `CLAUDE.md`**

Overwrite `CLAUDE.md` with:

````markdown
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Python 3.12 package (`droplet_lab`) that runs droplet-generation lab experiments
on a Windows lab PC. One YAML file per experiment drives an Ismatec MZR-7245
pump, a Keysight oscilloscope (VISA), a Nikon DSLR (via DigiCamControl HTTP)
and an optional Sartorius scale. Every device has a paired `Fake*`
implementation, so the full stack runs on macOS/Linux without hardware.

## Commands

```bash
uv sync --all-extras                # install / refresh deps
uv run droplet --version            # smoke test
uv run droplet validate experiments/example_hpmc.yaml
uv run droplet run    experiments/example_hpmc.yaml --simulate --no-confirm

uv run pytest                       # all tests
uv run pytest tests/integration -v  # end-to-end with fakes
uv run pytest -k <substring>        # subset
uv run pytest --cov=droplet_lab --cov-report=term-missing

uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pre-commit run --all-files
```

## Architecture

Single process. The CLI (`src/droplet_lab/cli.py`) loads a YAML into a
validated `ExperimentConfig` (pydantic v2), builds devices via factories in
`devices/__init__.py` (real or fake per `--simulate`), then hands off to
`Orchestrator` (`orchestrator.py`).

The orchestrator owns the experiment lifecycle: it creates the
`ExperimentDirectory` (`storage.py`), spawns `PumpWorker` and `ScopeWorker`
threads (and `ScaleWorker` if enabled), then walks the ramp profile. For each
step it updates the shared `ExperimentState` (so the scope worker tags every
sample with the current step + RPM), waits for stabilization, runs
`run_camera_capture` synchronously with a watchdog, and writes `step.json`. On
any error or `Ctrl-C` it sets `stop_event`, joins all worker threads via an
`ExitStack`, and writes a final `experiment.json` with status.

Coordination between threads is in-process only — `queue.Queue` for pump
commands, `threading.Event` for stop/error signalling, a `Lock`-guarded
`ExperimentState` for the current step. There is no file-based IPC.

Hardware is hidden behind four `typing.Protocol`s in `devices/base.py`. Real
implementations live alongside their fakes in the same directory; tests for
real classes mock `serial.Serial` / `pyvisa.ResourceManager` / `requests.get`
and never touch hardware.

## Things to know when editing

* `_StrictModel` in `config.py` sets `extra="forbid"` and `frozen=True` — every
  pydantic model in this codebase rejects unknown fields and is immutable. Use
  `model_copy(update=...)` to derive variants.
* `ExperimentState` is the only shared mutable state between threads. Always
  go through `update()` / `snapshot()` — never poke `_snapshot` directly.
* Loguru is the only logger. Threads bind a `component` extra (`pump`, `scope`,
  `camera`, `orchestrator`) so the file sink is filterable. Don't use the
  stdlib `logging` module.
* All timestamps are UTC ISO 8601 with microseconds and a `Z` suffix
  (`utc_now_iso` in `storage.py`). Folder names use a Windows-safe variant
  (`utc_now_filename_safe`).
* CSV writers use `;` and UTF-8 (DE-Excel compatible). `None` cells serialize
  as empty strings, not `"None"`.
* Workers must never raise; they catch, log, set `error_event`, and exit.
* The Keysight scope returns `~9.91e+37` to mean "no signal". `_safe_float` in
  `oscilloscope_keysight.py` filters this; preserve that behavior.
* `--simulate` is all-or-nothing today. Per-device simulation is doable
  (factory accepts `simulate=False` and you swap the Real for a Fake before
  passing into the orchestrator) but isn't wired into the CLI.
````

- [ ] **Step 2: Stage**

```bash
git add CLAUDE.md
```

Suggested commit message: `docs(claude): update CLAUDE.md to new package layout`

---

## Task 26: Delete legacy code

**Files:**
- Delete: `MASTER/`
- Delete: `PUMP/`
- Delete: `OSCILLOSCOPE/`
- Delete: `CAMERA/`
- Delete: `SCALE_SARTORIUS/`

- [ ] **Step 1: Verify nothing in the new code references old paths**

Run:
```bash
grep -r "MASTER/\|PUMP/\|OSCILLOSCOPE/\|CAMERA/\|SCALE_SARTORIUS/" src tests experiments docs README.md CLAUDE.md
```
Expected: no matches.

- [ ] **Step 2: Remove the legacy directories**

```bash
git rm -r MASTER PUMP OSCILLOSCOPE CAMERA SCALE_SARTORIUS
```

- [ ] **Step 3: Run the full test suite + lint + types one more time**

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
```
Expected: all green.

- [ ] **Step 4: Stage (git rm already staged the deletions)**

No additional staging needed — verify with `git status`.

Suggested commit message: `chore: remove legacy MASTER/PUMP/OSCILLOSCOPE/CAMERA/SCALE_SARTORIUS scripts`

---

## Final verification checklist

After all 26 tasks are committed by the user:

- [ ] `uv run pytest -v` — every test green.
- [ ] `uv run pytest --cov=droplet_lab --cov-report=term-missing` — coverage ≥ 90% on `orchestrator`, `config`, `state`, `storage`, `*_fake.py`.
- [ ] `uv run ruff check .` — no findings.
- [ ] `uv run ruff format --check .` — no diffs.
- [ ] `uv run mypy src tests` — Success.
- [ ] `uv run droplet validate experiments/example_hpmc.yaml` — `OK`.
- [ ] `uv run droplet run experiments/example_hpmc.yaml --simulate --no-confirm --no-tui` — completes; output folder under the YAML's `base_dir` contains `experiment.json` with `"status": "completed"`, `pump.csv`, `oscilloscope.csv`, two step folders each with `step.json` and an `images/` subdirectory.
- [ ] CI workflow runs green on macOS, Ubuntu, and Windows.
- [ ] Top-level repo no longer contains `MASTER/`, `PUMP/`, `OSCILLOSCOPE/`, `CAMERA/`, `SCALE_SARTORIUS/`.
