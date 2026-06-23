from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from droplet_lab.cli import app
from droplet_lab.displacement import (
    CalibrationCurve,
    CalibrationMeasurement,
    CalibrationModel,
    save_calibration_model,
)

runner = CliRunner()


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


def _write_model(path: Path) -> None:
    save_calibration_model(
        CalibrationModel(
            version=1,
            created_at_utc="2026-06-19T00:00:00Z",
            vibrometer_factor_um_per_v=1000.0,
            amplifier_gain=2.0,
            curves=[
                CalibrationCurve(
                    frequency_hz=20.0,
                    safe_max_amplitude_vpp=5.0,
                    measurements=[
                        CalibrationMeasurement(1.0, 1.0, 1000.0, [1000.0]),
                        CalibrationMeasurement(3.0, 3.0, 3000.0, [3000.0]),
                    ],
                )
            ],
        ),
        path,
    )


def test_validate_ok(tmp_path: Path) -> None:
    yml = _write_minimal_yaml(tmp_path)
    res = runner.invoke(app, ["validate", str(yml)])
    assert res.exit_code == 0, res.output
    assert "OK" in res.output


def test_validate_rejects_bad_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("experiment_id: TEST\n")  # missing required fields
    res = runner.invoke(app, ["validate", str(bad)])
    assert res.exit_code != 0


def test_validate_reports_combination_count(tmp_path: Path) -> None:
    yml = _write_minimal_yaml(tmp_path)
    res = runner.invoke(app, ["validate", str(yml)])
    assert res.exit_code == 0, res.output
    assert "1 combinations" in res.output


def test_dry_run_prints_plan(tmp_path: Path) -> None:
    yml = _write_minimal_yaml(tmp_path)
    res = runner.invoke(app, ["run", str(yml), "--dry-run", "--no-confirm", "--simulate"])
    assert res.exit_code == 0, res.output
    assert "200" in res.output


def test_dry_run_uses_randomized_sweep_order(tmp_path: Path) -> None:
    yml = _write_minimal_yaml(tmp_path)
    data = yaml.safe_load(yml.read_text())
    data["sweep"].update(
        {
            "speeds_rpm": [200, 800],
            "frequencies_hz": [20.0, 25.0],
            "amplitudes_vpp": [3.0, 5.0],
            "random": True,
        }
    )
    yml.write_text(yaml.safe_dump(data))

    res = runner.invoke(app, ["run", str(yml), "--dry-run", "--no-confirm", "--simulate"])

    assert res.exit_code == 0, res.output
    assert "random=True" in res.output
    lines = [line.strip() for line in res.output.splitlines() if line.strip().startswith("combo")]
    assert [line.split(":")[0] for line in lines] == [
        "combo 005",
        "combo 002",
        "combo 006",
        "combo 003",
        "combo 001",
        "combo 004",
        "combo 008",
        "combo 007",
    ]


def test_dry_run_prints_displacement_targets_and_resolved_voltage(tmp_path: Path) -> None:
    yml = _write_minimal_yaml(tmp_path)
    model_path = tmp_path / "model.json"
    _write_model(model_path)
    data = yaml.safe_load(yml.read_text())
    data["vibrometer"]["factor_um_per_v"] = 1000.0
    data["sweep"].pop("amplitudes_vpp")
    data["sweep"]["displacements_um"] = [2000.0]
    data["displacement"] = {"model_path": str(model_path)}
    yml.write_text(yaml.safe_dump(data))

    res = runner.invoke(app, ["run", str(yml), "--dry-run", "--no-confirm", "--simulate"])

    assert res.exit_code == 0, res.output
    assert "disp=[2000.0] um" in res.output
    assert "amp=2.0Vpp" in res.output
    assert "target=2000um" in res.output


def test_run_validation_prints_warning_table(tmp_path: Path) -> None:
    yml = _write_minimal_yaml(tmp_path)
    model_path = tmp_path / "model.json"
    _write_model(model_path)
    data = yaml.safe_load(yml.read_text())
    data["vibrometer"]["factor_um_per_v"] = 1000.0
    data["sweep"].pop("amplitudes_vpp")
    data["sweep"]["displacements_um"] = [2000.0]
    data["displacement"] = {
        "model_path": str(model_path),
        "validation_enabled": True,
        "validation_threshold_percent": 1.0,
        "measurement_s": 0.01,
        "scope_interval_s": 0.001,
    }
    yml.write_text(yaml.safe_dump(data))

    res = runner.invoke(app, ["run", str(yml), "--simulate", "--no-confirm", "--no-tui"])

    assert res.exit_code == 0, res.output
    assert "Displacement validation" in res.output
    assert "WARNING" in res.output


def test_calibrate_displacement_simulated_writes_model_and_csv(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    limits_path = tmp_path / "limits.xlsx"
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.append(["Frequency [Hz]", "max. Voltage [V]"])
    worksheet.append([10.0, 4.0])
    worksheet.append([20.0, 4.0])
    workbook.save(limits_path)

    yml = _write_minimal_yaml(tmp_path)
    model_path = tmp_path / "calibration.json"
    data = yaml.safe_load(yml.read_text())
    data["vibrometer"]["factor_um_per_v"] = 1000.0
    data["displacement"] = {
        "model_path": str(model_path),
        "max_voltage_table_path": str(limits_path),
        "calibration_start_hz": 10.0,
        "calibration_stop_hz": 10.0,
        "calibration_step_hz": 10.0,
        "voltage_steps": 2,
        "measurement_s": 0.01,
        "scope_interval_s": 0.001,
    }
    yml.write_text(yaml.safe_dump(data))

    res = runner.invoke(app, ["calibrate-displacement", str(yml), "--simulate", "--no-confirm"])

    assert res.exit_code == 0, res.output
    assert model_path.exists()
    assert model_path.with_suffix(".csv").exists()
    assert "calibrated 1 frequencies" in res.output


def test_run_simulate_completes(tmp_path: Path) -> None:
    yml = _write_minimal_yaml(tmp_path)
    res = runner.invoke(app, ["run", str(yml), "--simulate", "--no-confirm", "--no-tui"])
    assert res.exit_code == 0, res.output
    runs = list(tmp_path.iterdir())
    # at least the YAML and one experiment folder exist
    assert any(p.name != "exp.yaml" for p in runs)


def test_simulate_only_accepts_csv(tmp_path: Path) -> None:
    yml = _write_minimal_yaml(tmp_path)
    res = runner.invoke(
        app,
        [
            "run",
            str(yml),
            "--simulate-only",
            "pump,scope,camera,function_generator,scale",
            "--no-confirm",
            "--no-tui",
        ],
    )
    assert res.exit_code == 0, res.output


def test_simulate_only_accepts_function_generator(tmp_path: Path) -> None:
    yml = _write_minimal_yaml(tmp_path)
    result = runner.invoke(
        app,
        [
            "run",
            str(yml),
            "--simulate-only",
            "function_generator",
            "--no-confirm",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output


def test_run_rejects_real_arduino_camera_sharing_real_pump_port(tmp_path: Path) -> None:
    yml = _write_minimal_yaml(tmp_path)
    data = yaml.safe_load(yml.read_text())
    data["devices"]["camera"].update(
        {
            "trigger_backend": "arduino",
            "shutter_port": "COM3",
        }
    )
    yml.write_text(yaml.safe_dump(data))

    result = runner.invoke(
        app,
        [
            "run",
            str(yml),
            "--simulate-only",
            "scope,scale,function_generator",
            "--dry-run",
            "--no-confirm",
        ],
    )

    assert result.exit_code != 0
    assert "Arduino shutter port COM3" in result.output
    assert "pump" in result.output


def test_run_allows_arduino_camera_sharing_simulated_pump_port(tmp_path: Path) -> None:
    yml = _write_minimal_yaml(tmp_path)
    data = yaml.safe_load(yml.read_text())
    data["devices"]["camera"].update(
        {
            "trigger_backend": "arduino",
            "shutter_port": "COM3",
        }
    )
    yml.write_text(yaml.safe_dump(data))

    result = runner.invoke(
        app,
        [
            "run",
            str(yml),
            "--simulate-only",
            "pump,scope,scale,function_generator",
            "--dry-run",
            "--no-confirm",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "--dry-run: not executing" in result.output


def test_simulate_only_rejects_unknown_device(tmp_path: Path) -> None:
    yml = _write_minimal_yaml(tmp_path)
    result = runner.invoke(app, ["run", str(yml), "--simulate-only", "bogus"])
    assert result.exit_code != 0
    assert "bogus" in result.output
    assert "function_generator" in result.output


def test_simulate_only_rejects_unknown_device_legacy(tmp_path: Path) -> None:
    yml = _write_minimal_yaml(tmp_path)
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
