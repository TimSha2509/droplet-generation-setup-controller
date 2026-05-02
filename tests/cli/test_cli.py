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
        "timing": {
            "stabilization_s": 0.05,
            "image_interval_s": 0.1,
            "camera_latency_tolerance_s": 0.05,
        },
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
