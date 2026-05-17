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
    CameraConfig,
    DevicesConfig,
    ExperimentConfig,
    FunctionGeneratorConfig,
    LimitsConfig,
    OscilloscopeConfig,
    OutputConfig,
    PumpConfig,
    ScaleConfig,
    SweepConfig,
    TimingConfig,
    VibrometerConfig,
    load_experiment,
)
from droplet_lab.devices import (
    build_camera,
    build_function_generator,
    build_oscilloscope,
    build_pump,
    build_scale,
)
from droplet_lab.orchestrator import DeviceBundle, Orchestrator
from droplet_lab.state import ExperimentState, ExperimentStatus
from droplet_lab.sweep import expand_sweep

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


def _combo_count(cfg: ExperimentConfig) -> int:
    return (
        len(cfg.sweep.speeds_rpm)
        * len(cfg.sweep.frequencies_hz)
        * len(cfg.sweep.amplitudes_vpp)
    )


@app.command()
def validate(yaml_path: Path) -> None:
    """Validate an experiment YAML without opening any hardware."""
    cfg = load_experiment(yaml_path)
    typer.echo(f"OK: {cfg.experiment_id} ({_combo_count(cfg)} combinations)")


_VALID_SIMULATE_ONLY = {"pump", "scope", "camera", "function_generator", "scale"}


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
        typer.Option(
            "--simulate",
            help="Use all fake devices (pump, scope, camera, function_generator, scale)",
        ),
    ] = False,
    simulate_only: Annotated[
        str | None,
        typer.Option(
            "--simulate-only",
            help="Comma-separated list of devices to mock "
            "(pump,scope,camera,function_generator,scale)",
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

    n_combos = _combo_count(cfg)
    typer.echo(f"Experiment: {cfg.experiment_id}  nozzle={cfg.nozzle_id}")
    typer.echo(
        f"Sweep: rpm={list(cfg.sweep.speeds_rpm)}  "
        f"freq={list(cfg.sweep.frequencies_hz)} Hz  "
        f"amp={list(cfg.sweep.amplitudes_vpp)} Vpp  "
        f"hold={cfg.sweep.hold_s} s  ({n_combos} combinations)"
    )
    if fakes:
        typer.echo(f"Simulated devices: {sorted(fakes)}")

    if dry_run:
        for c in expand_sweep(
            speeds_rpm=list(cfg.sweep.speeds_rpm),
            frequencies_hz=list(cfg.sweep.frequencies_hz),
            amplitudes_vpp=list(cfg.sweep.amplitudes_vpp),
            hold_s=cfg.sweep.hold_s,
        ):
            typer.echo(
                f"  combo {c.combo_index:03d}: rpm={c.set_speed_rpm}  "
                f"freq={c.frequency_hz}Hz  amp={c.amplitude_vpp}Vpp  "
                f"(changed={c.changed})"
            )
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
        "function_generator": build_function_generator(
            cfg.devices.function_generator,
            simulate="function_generator" in fakes,
        ),
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
        vibrometer=VibrometerConfig(factor_um_per_v=5280),
        sweep=SweepConfig(
            speeds_rpm=[200, 800, 1000],
            frequencies_hz=[20.0, 25.0, 30.0],
            amplitudes_vpp=[3.0, 5.0, 9.0],
            hold_s=30.0,
        ),
        timing=TimingConfig(
            stabilization_rpm_change_s=10.0,
            stabilization_freq_change_s=3.0,
            stabilization_amp_change_s=1.0,
            image_interval_s=5.0,
            camera_latency_tolerance_s=1.0,
        ),
        limits=LimitsConfig(max_speed_rpm=1000),
        devices=DevicesConfig(
            pump=PumpConfig(port="COM3"),
            oscilloscope=OscilloscopeConfig(visa_resource="USB0::0xXXXX::INSTR"),
            camera=CameraConfig(),
            function_generator=FunctionGeneratorConfig(port="COM4"),
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
