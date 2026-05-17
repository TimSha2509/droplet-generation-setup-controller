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
    exp.append_runs_row(row)
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
