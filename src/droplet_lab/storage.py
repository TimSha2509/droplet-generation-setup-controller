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
