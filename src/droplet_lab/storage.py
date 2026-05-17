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


def combo_folder_name(
    combo_index: int, set_speed_rpm: int, frequency_hz: float, amplitude_vpp: float
) -> str:
    """Stable, sortable name for one combination's step folder.

    Format: ``combo_<NNN>_rpm<RRRR>_f<FREQ>Hz_amp<AMP>V``.
    """
    return (
        f"combo_{combo_index:03d}_rpm{set_speed_rpm:04d}_f{frequency_hz:g}Hz_amp{amplitude_vpp:g}V"
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
    def scale_csv_path(self) -> Path:
        return self.root / "scale.csv"

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

    def _append_row(self, path: Path, row: Any, row_cls: type) -> None:
        fieldnames = _fieldnames_for(row_cls)
        is_new = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=fieldnames, delimiter=";")
            if is_new:
                writer.writeheader()
            data = asdict(row)
            sanitized = {k: ("" if v is None else v) for k, v in data.items()}
            writer.writerow(sanitized)

    def append_scale_row(self, row: ScaleRow) -> None:
        """Append one row to scale.csv (creates the file + header on first call)."""
        self._append_row(self.scale_csv_path, row, ScaleRow)

    def append_runs_row(self, row: RunsRow) -> None:
        """Append one row to runs.csv (creates the file + header on first call)."""
        self._append_row(self.runs_csv_path, row, RunsRow)

    @staticmethod
    def write_json(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
