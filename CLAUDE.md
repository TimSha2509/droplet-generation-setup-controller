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
* Two CLI flags control simulation: `--simulate` (all four devices fake) and
  `--simulate-only pump,scope,camera,scale` (CSV subset). The factory in
  `devices/__init__.py` decides per-device based on the resulting set; unknown
  device names raise `typer.BadParameter`.
