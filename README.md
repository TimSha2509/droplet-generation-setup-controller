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
