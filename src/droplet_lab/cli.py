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
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit",
        ),
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
    simulate: Annotated[
        bool,
        typer.Option("--simulate", help="Use FakePump/FakeScope/FakeCamera/FakeScale"),
    ] = False,
    simulate_only: Annotated[
        str | None,
        typer.Option(
            "--simulate-only",
            help="Comma-separated list of devices to mock (pump,scope,camera,scale)",
        ),
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option(help="Override output.base_dir"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print the plan and exit"),
    ] = False,
    no_confirm: Annotated[
        bool,
        typer.Option("--no-confirm", help="Skip 'press Enter to start'"),
    ] = False,
    no_tui: Annotated[
        bool,
        typer.Option("--no-tui", help="Disable rich live display"),
    ] = False,
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
        "scope": build_oscilloscope(
            cfg.devices.oscilloscope, state=state, simulate="scope" in fakes
        ),
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
    except Exception as e:
        typer.echo(f"  (error: {e})")

    typer.echo("VISA resources:")
    try:
        import pyvisa

        rm = pyvisa.ResourceManager()
        for r in rm.list_resources():
            typer.echo(f"  {r}")
        rm.close()
    except Exception as e:
        typer.echo(f"  (error: {e})")
