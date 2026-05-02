import csv
import json
from pathlib import Path

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
    assert text.split("\n")[1].split(";").count("") >= 7


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
