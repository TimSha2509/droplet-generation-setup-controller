# Droplet Lab Controller — Refactor Design

**Status:** Draft for approval
**Date:** 2026-05-02
**Author:** Refactor brainstorming session
**Audience:** Maintainer (PhD candidate, Python beginner) and contributors

## 1. Goals

Replace the current collection of standalone scripts with a single, professionally-engineered Python package that controls the droplet-generation rig. The refactor is a full rewrite — no backwards compatibility with current file names, JSON shapes, or CSV columns is required (no downstream consumer exists yet).

Concrete goals:

1. **One process, one lifecycle** — replace the four-process / file-based-IPC architecture with a single Python process using threads and in-memory queues.
2. **Hardware abstraction** — every device (pump, oscilloscope, camera, scale) hides behind a typed `Protocol`, with a `Real*` and a `Fake*` implementation. Full experiments can be simulated on a laptop without any lab hardware.
3. **Declarative experiments** — every experiment is one validated YAML file under `experiments/`. No constants need to be edited in code to start a run.
4. **Modern, idiomatic Python 3.12** — `pyproject.toml`, `uv`, `pydantic` v2, `typer`, `loguru`, `pytest`, `ruff`, `mypy --strict`. Type hints everywhere.
5. **Onboarding-first README** — a beginner-friendly maintainer must be able to set up the dev environment, run a simulated experiment, and understand the output structure within an hour, without reading source code.

Non-goals (explicit YAGNI):

- No GUI/web UI.
- No database — CSV + JSON files on disk.
- No async/asyncio (`pyvisa` has no async support; threads are the right model here).
- No plugin/registry system — devices are wired in code.
- No realtime analysis pipeline.
- No Sphinx/mkdocs site — README + docstrings.
- No Docker — `uv` handles environments.

## 2. Architecture

### 2.1 Process model

A single Python process. Each long-running data acquisition device runs in its own thread; per-step camera capture runs in a short-lived thread with a watchdog. Threads coordinate via:

- `queue.Queue[PumpCommand]` — orchestrator → pump worker (set-speed commands).
- `threading.Event stop_event` — orchestrator → all workers (graceful shutdown).
- `threading.Event error_event` — any worker → orchestrator (fatal error notification).
- `ExperimentState` (dataclass behind a `threading.Lock`) — orchestrator updates the current `step_index` and `set_speed_rpm`; scope worker reads them when tagging measurements.

```
┌──────────────────────────────────────────────────────────────┐
│  cli.py (typer)                                              │
│      validate config → load YAML → ExperimentConfig          │
│      build devices (real vs fake based on --simulate)        │
│      hand to Orchestrator                                    │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│  Orchestrator (main thread)                                  │
│   ├─ creates ExperimentDirectory + writes experiment.json    │
│   ├─ starts PumpWorker thread, ScopeWorker thread            │
│   ├─ for each RampStep:                                      │
│   │     publish set_speed → pump cmd queue                   │
│   │     update shared ExperimentState (step, rpm)            │
│   │     wait stabilization                                   │
│   │     run CameraWorker for imaging_duration (with watchdog)│
│   │     write step metadata                                  │
│   └─ on stop/abort: signal workers, join, flush, write       │
└──────────────────────────────────────────────────────────────┘
        │                    │                       │
        ▼                    ▼                       ▼
   PumpWorker           ScopeWorker             CameraWorker
   ───────────          ───────────             ────────────
   Pump (Protocol)      Oscilloscope            Camera
    ├ MZR7245            ├ KeysightVisa          ├ DigiCamHttp
    └ FakePump           └ FakeOscilloscope      └ FakeCamera
```

### 2.2 Lifecycle and error handling

- Every device implements `__enter__`/`__exit__` (open/close connection).
- Orchestrator uses `contextlib.ExitStack` so all hardware is closed deterministically, even on exception.
- Each worker catches its own exceptions, logs with stacktrace, sets `error_event`, and exits.
- Orchestrator polls `error_event` on every wait tick; if set, it begins shutdown and writes `experiment.status = "failed"` with `failure_reason`.
- `Ctrl-C` sets `stop_event` for graceful shutdown. A second `Ctrl-C` within 2 seconds escalates to a hard exit.
- Camera watchdog: if `imaging_duration + camera_latency_tolerance_s` elapses without the camera worker finishing, the orchestrator signals it and marks the step `camera_timeout`.

### 2.3 Coordination, replacing today's file-based IPC

| Concern | Today | New |
|---|---|---|
| Master → pump `SET_SPEED` | `pump_command.txt` | `queue.Queue[PumpCommand]` |
| Master → pump `STOP` | `pump_command.txt` `STOP` | `stop_event` |
| Master → scope stop | `oscilloscope_stop.txt` | `stop_event` |
| Master → scope current step | `experiment_state.json` | `ExperimentState` + `Lock` |
| Master ↔ camera step status | `metadata.json` (read-modify-write) | Single-writer-per-key, no shared file |

## 3. Repository layout

```
droplet-generation-setup-controller/
├── pyproject.toml              # uv, ruff, mypy, pytest config
├── README.md                   # onboarding guide
├── CLAUDE.md                   # updated to new layout
├── .python-version             # 3.12
├── .pre-commit-config.yaml
├── .gitignore
├── .github/
│   └── workflows/ci.yml        # pytest + ruff + mypy on macOS/Linux/Windows
├── experiments/
│   ├── example_hpmc.yaml       # fully commented reference experiment
│   └── README.md               # field-by-field reference
├── src/droplet_lab/
│   ├── __init__.py
│   ├── __main__.py             # `python -m droplet_lab`
│   ├── cli.py                  # typer app
│   ├── config.py               # pydantic v2 models
│   ├── logging_setup.py        # loguru sinks (console + per-experiment file)
│   ├── orchestrator.py         # ramp loop, thread coordination, lifecycle
│   ├── state.py                # StrEnums + ExperimentState dataclass
│   ├── storage.py              # ExperimentDirectory, CSV writers, JSON metadata
│   ├── devices/
│   │   ├── __init__.py         # device factories: build_pump(...) etc.
│   │   ├── base.py             # Protocols + measurement dataclasses
│   │   ├── pump_mzr7245.py
│   │   ├── pump_fake.py
│   │   ├── oscilloscope_keysight.py
│   │   ├── oscilloscope_fake.py
│   │   ├── camera_digicam.py
│   │   ├── camera_fake.py
│   │   ├── scale_sartorius.py
│   │   └── scale_fake.py
│   └── workers/
│       ├── __init__.py
│       ├── pump_worker.py
│       ├── scope_worker.py
│       └── camera_worker.py
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_storage.py
│   │   └── test_state_transitions.py
│   ├── devices/
│   │   ├── test_pump_fake.py
│   │   ├── test_oscilloscope_fake.py
│   │   ├── test_camera_fake.py
│   │   └── test_scale_fake.py
│   └── integration/
│       └── test_orchestrator_end_to_end.py
└── docs/
    └── superpowers/specs/      # design docs
```

## 4. Device abstraction

### 4.1 Protocols

`devices/base.py` defines one `typing.Protocol` per device class. Each protocol also extends `AbstractContextManager`. Structural typing means fakes need no inheritance.

```python
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

Measurements are immutable dataclasses (`@dataclass(frozen=True, slots=True)`) — e.g. `ScopeMeasurement(frequency_hz, vpp_v, ch2_vrms_dc_v, ch3_vrms_dc_v)`.

### 4.2 Real implementations

- `MZR7245Pump` (in `pump_mzr7245.py`): `pyserial`-based, ports the existing class from `PUMP/pump_logger.py`. Adds context manager, structured logging, retry on transient `serial.SerialException`.
- `KeysightOscilloscope` (`oscilloscope_keysight.py`): `pyvisa`-based, ports the SCPI calls from `OSCILLOSCOPE/Oscilloscope_logger.py`.
- `DigiCamCamera` (`camera_digicam.py`): HTTP client against `http://localhost:5513`. Uses `requests` with explicit timeouts and retry on transient connection errors.
- `SartoriusScale` (`scale_sartorius.py`): `pyserial`, 7E1 framing as in the existing exploratory script. Promoted from a probe to a first-class device, optional in config.

### 4.3 Fake implementations

Each `Fake*` is fully self-contained, deterministic given a seed, and obeys its protocol exactly:

- `FakePump` — internal `current_rpm` interpolated toward `target_rpm` with a configurable acceleration; simulated temperature drift; jitter via injected `random.Random(seed)`.
- `FakeOscilloscope` — given a reference to the shared `ExperimentState`, returns plausible measurements correlated with `set_speed_rpm` (e.g. `vpp ~ a*rpm + noise`).
- `FakeCamera` — writes empty `.NEF` (or 1×1 placeholder JPEG) files into the configured output folder, named with a monotonic counter, so downstream tooling sees real files.
- `FakeScale` — emits a slowly-rising weight curve.

### 4.4 Device factory

`devices/__init__.py` exposes:

```python
def build_pump(cfg: PumpConfig, *, simulate: bool) -> Pump: ...
def build_oscilloscope(cfg: OscilloscopeConfig, *, simulate: bool) -> Oscilloscope: ...
def build_camera(cfg: CameraConfig, *, simulate: bool) -> Camera: ...
def build_scale(cfg: ScaleConfig, *, simulate: bool) -> Scale: ...
```

CLI flag `--simulate` forces all to fake; `--simulate-only pump,scale` is selective.

## 5. Configuration

### 5.1 Example YAML

```yaml
# experiments/example_hpmc.yaml
experiment_id: HPMC_Test_01
nozzle_id: 1mm_A

actuation:
  frequency_hz: 200
  voltage_v: 5
  vibrometer_factor_um_per_v: 5280

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
    port: COM5

output:
  base_dir: 'W:\PROMOTION_SHARIFSOLTANI_VERKAPSELUNG_DFG_TH1817_9_1_MT\PYTHON\Project_files\DATA'
```

### 5.2 Pydantic models

- `ExperimentConfig` — top-level, root model.
- `ActuationConfig` — `frequency_hz: PositiveFloat`, `voltage_v: PositiveFloat`, `vibrometer_factor_um_per_v: PositiveFloat`.
- `RampStep` — `speed_rpm: PositiveInt`, `hold_s: PositiveFloat`.
- `RampProfile` — `list[RampStep]`, `min_length=1`. Cross-field validator ensures every `speed_rpm <= limits.max_speed_rpm`.
- `TimingConfig` — `stabilization_s: NonNegativeFloat`, `image_interval_s: PositiveFloat`, `camera_latency_tolerance_s: NonNegativeFloat`.
- `DevicesConfig` — nested `PumpConfig`, `OscilloscopeConfig`, `CameraConfig`, `ScaleConfig`.
- `OutputConfig` — `base_dir: Path`. Validator resolves to absolute path; existence check is opt-in (CLI `--create-dirs`).

All models use `model_config = ConfigDict(extra="forbid")` so typos in YAML fail loudly.

## 6. Output schema

```
<base_dir>/<UTC-ISO-timestamp>__<experiment_id>/
├── experiment.json              # ExperimentConfig + run metadata + final status
├── experiment.log               # loguru file sink (all threads, all levels)
├── pump.csv                     # ; separated, UTF-8, header row
├── oscilloscope.csv             # ; separated
├── scale.csv                    # only if scale enabled
└── steps/
    ├── step_01_200rpm/
    │   ├── step.json            # step metadata + final status + capture count
    │   └── images/              # camera writes raw files here
    └── step_02_250rpm/
```

All timestamps are **UTC ISO 8601** (`2026-05-02T14:32:01.123456Z`). Folder timestamp uses the same format with `:` replaced by `-` for filesystem safety.

CSV column orders are fixed (and tested):

- `pump.csv`: `timestamp_utc;elapsed_s;step_index;set_speed_rpm;actual_speed_rpm;temperature_c`
- `oscilloscope.csv`: `timestamp_utc;elapsed_s;step_index;set_speed_rpm;frequency_hz;vpp_v;p2p_displacement_um;ch2_vrms_dc_v;ch3_vrms_dc_v`
- `scale.csv`: `timestamp_utc;elapsed_s;step_index;set_speed_rpm;weight_g`

`experiment.json` and `step.json` are pydantic dumps (`model_dump_json(indent=2)`) of dedicated state models — schema is type-checked, never assembled ad-hoc.

## 7. State machine

`state.py` defines `StrEnum`s:

```python
class ExperimentStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    ABORTED = "aborted"          # user-requested stop
    FAILED = "failed"            # error during run

class StepStatus(StrEnum):
    PLANNED = "planned"
    STABILIZING = "stabilizing"
    IMAGING = "imaging"
    COMPLETED = "completed"
    COMPLETED_NO_IMAGING = "completed_no_imaging"
    CAMERA_TIMEOUT = "camera_timeout"
    CAMERA_FAILED = "camera_failed"
    ABORTED = "aborted"
```

All transitions happen in `orchestrator.py` and are unit-tested. A `camera_failed` step transitions the whole experiment to `FAILED`.

## 8. CLI

Entry point exposed by `[project.scripts]` as `droplet`:

```
droplet run <experiment.yaml>           # main
  --simulate                            # all devices as fakes
  --simulate-only pump,scale            # selective
  --output-dir PATH                     # override base_dir
  --dry-run                             # validate + print plan, no hardware
  --no-confirm                          # skip "press Enter to start"
  --no-tui                              # disable rich live status

droplet validate <experiment.yaml>      # pydantic-only, no hardware
droplet list-devices                    # lists COM ports + VISA resources
droplet new <name>                      # scaffold experiments/<name>.yaml
droplet --version

# Debug subcommands (single-device probes, optional)
droplet pump-test --port COM3 --rpm 200 --duration-s 10
droplet scope-probe --visa <resource>
```

Optional `rich.live` status table during a run, suppressible for CI/headless logs.

## 9. Logging

`logging_setup.setup_logging(experiment_dir, level=...)` configures loguru with two sinks:

- **Console** — INFO+, colored, format `HH:MM:SS | LEVEL | component | message`.
- **File** — DEBUG+, UTC timestamps with millisecond precision, includes `name:function:line`, `enqueue=True` for thread-safe writes. Lives at `<experiment_dir>/experiment.log`.

Each thread binds a `component` label: `logger.bind(component="pump")`, `..."scope"`, `..."camera"`, `..."orchestrator"`. Hardware-level reads log at DEBUG. Errors that abort the experiment use `logger.exception(...)` for full stacktrace.

## 10. Tests

Three layers, none requiring hardware:

| Layer | Scope |
|---|---|
| Unit (`tests/unit/`) | Pydantic validation, state transitions, CSV writers, path helpers, ExperimentDirectory layout |
| Device (`tests/devices/`) | Each fake exercised against its `Protocol`; determinism checks with fixed seeds |
| Integration (`tests/integration/`) | Full orchestrator runs with all fakes, tmp_path output, end-to-end artifact checks |

Key fixtures (`tests/conftest.py`):

- `fake_devices` — bundle of seeded fakes.
- `minimal_config(tmp_path)` — 2-step ramp with sub-second timings for fast tests.
- `experiment_dir(tmp_path)` — empty `ExperimentDirectory`.

Required E2E coverage:

- `test_full_ramp_writes_expected_artifacts` — completed status, all CSVs/JSONs present, row counts match.
- `test_ctrl_c_aborts_cleanly` — stop_event mid-run, all threads joined, files closed, status `aborted`.
- `test_camera_failure_aborts_experiment` — `FakeCamera.fail_on_step(2)`, experiment status `failed`, step status `camera_failed`.
- `test_camera_timeout_terminates_step` — `FakeCamera.hang()`, watchdog fires, step status `camera_timeout`.
- `test_validate_rejects_speed_over_limit`.
- `test_simulate_only_mixes_real_and_fake` (mocks the `RealPump.__enter__`).

Coverage target ≥ 90% on `orchestrator.py`, `config.py`, `state.py`, `storage.py`, all `*_fake.py` modules. Real device classes get smoke tests against a serial loopback or `pyserial-mock` where feasible.

CI (`.github/workflows/ci.yml`) runs `uv sync && uv run pytest && uv run ruff check && uv run mypy src` on macOS, Ubuntu, Windows for Python 3.12.

## 11. Tooling stack

| Concern | Tool |
|---|---|
| Package & env | `uv` |
| Build manifest | `pyproject.toml` (PEP 621) |
| Python | 3.12 (pinned via `.python-version`) |
| Lint + format | `ruff` |
| Type checking | `mypy --strict` |
| Tests | `pytest`, `pytest-cov` |
| CLI | `typer` |
| Logging | `loguru` |
| Config | `pydantic` v2 + `pyyaml` |
| Pre-commit | `pre-commit` (ruff, mypy, end-of-file-fixer) |

## 12. README structure

The README is the primary onboarding document. Sections:

1. **What this is** — three-sentence overview.
2. **Hardware overview** — table of devices, models, connections, required external software (DigiCamControl, NI-VISA, COM port assignment).
3. **One-time setup** — install `uv`, clone, `uv sync`, `uv run droplet --version`, DigiCamControl HTTP server config, NI-VISA install, identify COM ports with `droplet list-devices`.
4. **Quick start — your first experiment** — `droplet new`, edit YAML, `droplet validate`, `droplet run --simulate`, `droplet run`. What `Ctrl-C` does, what graceful shutdown looks like.
5. **Experiment configuration reference** — every YAML field with type, unit, default, description.
6. **Output** — directory structure, CSV columns, JSON schema, mini pandas-loading example.
7. **Common workflows** — new experiment type, run with selective simulation, locate and inspect logs.
8. **Troubleshooting** — symptom · cause · fix table for COM3 conflicts, VISA timeouts, DigiCamControl 404, network share permissions, missing `uv`.
9. **Developer guide** — repo structure diagram, run tests, run lint/typecheck, how to add a new device (Protocol + Real + Fake + Worker + Test, step by step).

Conventions: every executable command in its own copy-ready code block; platform-specific commands tagged (`# Windows (PowerShell)` vs `# macOS/Linux`); no "see code comment" cross-references.

## 13. Migration

Big-bang rewrite in a single feature branch. The old top-level directories (`MASTER/`, `PUMP/`, `CAMERA/`, `OSCILLOSCOPE/`, `SCALE_SARTORIUS/`) are deleted in the same commit set. No parallel-running window — nothing depends on the current outputs.

| Existing file | New home | Action |
|---|---|---|
| `MASTER/run_master.py` | `orchestrator.py` + `cli.py` | Logic ported, file deleted |
| `PUMP/pump_logger.py` | `devices/pump_mzr7245.py` + `workers/pump_worker.py` | Class extracted, file-IPC removed |
| `PUMP/control_mzr7245.py` | merged into above | Standalone CLI exposed as `droplet pump-test` debug subcommand |
| `PUMP/ControlArduino.py`, `ControlArduino2.py` | — | Deleted (broken, unused) |
| `OSCILLOSCOPE/Oscilloscope_logger.py` | `devices/oscilloscope_keysight.py` + `workers/scope_worker.py` | Ported |
| `OSCILLOSCOPE/Oscilloscope_test.py` | merged or deleted | Promote to `droplet scope-probe` debug subcommand if useful, else delete |
| `CAMERA/Nikon_control.py` | `devices/camera_digicam.py` + `workers/camera_worker.py` | Ported |
| `CAMERA/DIGICAM_CONTROL/*` | — | Deleted (exploratory, redundant) |
| `SCALE_SARTORIUS/Script_read_Scale.py` | `devices/scale_sartorius.py` | Promoted to first-class device |

`CLAUDE.md` updated in the same commit set to reflect the new layout, build/test commands, and architecture.

## 14. Open questions

None remaining. All decisions confirmed by the user during brainstorming:

- Architecture: monolithic process with threads (option A in Frage 4).
- Configuration: pydantic + per-experiment YAML (option A in Frage 5).
- Hardware simulation: full Fake implementations per device (option A in Frage 6).
- Python version: 3.12 (option A in Frage 7).
- Output format: CSV stays (option A in Frage 8).
- Documentation language: English throughout (corrected during Frage 9).
- CI: GitHub Actions workflow included (option A in CI question).
