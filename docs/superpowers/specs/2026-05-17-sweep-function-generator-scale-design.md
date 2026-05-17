# Sweep über RPM × Frequenz × Amplitude, Function Generator & Waagen-Verbesserungen

**Status:** Design genehmigt 2026-05-17
**Quelle:** `new_files/ReadMe.md`, `new_files/Function_generator.py`, `new_files/Script_read_Scale_v2.py`

## Ziel

Das Experiment-System um drei Bausteine erweitern:

1. **Sweep statt einzelner Ramp:** Im YAML werden Listen von Drehzahlen, Frequenzen und Spannungs-Amplituden angegeben. Das Programm fährt das volle Kreuzprodukt ab — Hierarchie `RPM außen → Frequenz → Amplitude innen`.
2. **Neuer Function Generator (PSG9080)** als eigenes Device mit Real- und Fake-Implementierung. Treibt Sinus auf konfiguriertem Kanal, hartes Sicherheits-Limit 9.5 Vpp.
3. **Scale-Verbesserungen:** Initiales Gewicht vor dem ersten Pumpen-Start einmalig speichern; Logging-Intervall konfigurierbar (Default 5 s).

Zusätzlich werden die zwei TODOs aus dem ReadMe abgearbeitet: Roh-Daten (Pump-/Scope-CSV) pro Step in den Step-Ordner, und ein durchsuchbarer `runs.csv`-Batch-Report pro Experiment.

Mittelfristig soll das gesamte Setup in eine Datenbank wandern, die per Pfad auf die Roh-Daten referenziert. Das Design ist so gewählt, dass jeder Step-Ordner ein in sich geschlossener Run mit allen zugehörigen Roh-Daten ist — sauberer Input für einen späteren DB-Importer.

## Umsetzungsstrategie

Big-Bang Schema-Wechsel: alte YAML-Felder (`ramp`, `actuation`) werden ersetzt. Es gibt keinen Kompatibilitäts-Pfad — Projekt ist intern, keine externen YAML-Konsumenten.

## YAML-Schema

```yaml
experiment_id: HPMC_Test_01
nozzle_id: 1mm_A

vibrometer:
  factor_um_per_v: 5280

sweep:
  speeds_rpm:      [200, 800, 1000]
  frequencies_hz:  [20, 25, 30]
  amplitudes_vpp:  [3.0, 5.0, 9.0]
  hold_s: 30

timing:
  stabilization_rpm_change_s:  10
  stabilization_freq_change_s: 3
  stabilization_amp_change_s:  1
  image_interval_s: 5
  camera_latency_tolerance_s: 1.0

limits:
  max_speed_rpm: 1000

devices:
  pump:
    port: COM3
    baudrate: 9600
  oscilloscope:
    visa_resource: "USB0::0x2A8D::0x1778::MY55440264::0::INSTR"
  camera:
    digicam_url: "http://localhost:5513"
  function_generator:
    port: COM4
    channel: 1
    baudrate: 115200
  scale:
    enabled: false
    port: null
    baudrate: 1200
    interval_s: 5

output:
  base_dir: 'W:\...\DATA'
```

### Validierung (Pydantic, alle `_StrictModel` wie bisher)

- Jede `amplitudes_vpp` muss `≤ 9.5` sein (`MAX_AMPLITUDE_VPP = 9.5`, im Code als Modul-Konstante).
- Jede `speeds_rpm` muss `≤ limits.max_speed_rpm` sein.
- Alle drei Sweep-Listen müssen non-empty sein.
- `function_generator.channel ∈ {1, 2}`.
- `hold_s` muss `>= stabilization_rpm_change_s` sein (Worst-Case-Stabilisierung). Bei Combos mit `changed in ("freq","amp")` wird `imaging_duration = hold_s - stabilization_for(changed)` entsprechend größer.

## Sweep-Modell

```python
@dataclass(frozen=True, slots=True)
class SweepCombination:
    combo_index: int                  # 1-basiert
    set_speed_rpm: int
    frequency_hz: float
    amplitude_vpp: float
    hold_s: float
    changed: Literal["initial", "rpm", "freq", "amp"]
```

`SweepConfig.expand()` iteriert mit drei verschachtelten Schleifen `for rpm in speeds_rpm: for freq in frequencies_hz: for amp in amplitudes_vpp:` und erzeugt die Combos fortlaufend nummeriert. `changed` wird gegenüber der vorigen Combo gesetzt:

| Vorgänger → Aktuell | `changed` |
|---|---|
| keiner (erste Combo) | `"initial"` |
| RPM hat sich geändert | `"rpm"` |
| RPM gleich, Freq geändert | `"freq"` |
| RPM und Freq gleich, Amp geändert | `"amp"` |

Die Wartezeit nach einer Combo-Änderung wird aus `changed` abgeleitet:

| `changed` | Wartezeit |
|---|---|
| `initial` / `rpm` | `stabilization_rpm_change_s` |
| `freq` | `stabilization_freq_change_s` |
| `amp` | `stabilization_amp_change_s` |

## Shared State

`ExperimentState` bekommt zusätzlich `combo_index`, `set_frequency_hz`, `set_amplitude_vpp` — analog zur bestehenden `set_speed_rpm`. `ExperimentStateSnapshot` und `update()` werden um diese Felder erweitert. Worker (Pump, Scope, Scale) lesen den Snapshot wie bisher und taggen jede ihrer Sample-Zeilen mit der vollen Kombi.

## Function Generator

### Protocol (`devices/base.py`)

```python
class FunctionGenerator(Protocol, AbstractContextManager["FunctionGenerator"]):
    def set_sine(self) -> None: ...
    def set_frequency_hz(self, hz: float) -> None: ...
    def set_amplitude_vpp(self, vpp: float) -> None: ...    # raises ValueError if > 9.5
    def enable_output(self, on: bool) -> None: ...
```

### `PSG9080Generator` (`devices/function_generator_psg9080.py`)

Aufgesetzt auf `new_files/Function_generator.py`. Kanal wird im Konstruktor übergeben. Befehlsformate bleiben identisch zum vorhandenen Script:

| Aktion | Channel 1 | Channel 2 |
|---|---|---|
| Sinus | `:w11=0.` | `:w12=0.` |
| Frequenz (Hz × 1000) | `:w13={n},0.` | `:w14={n},0.` |
| Amplitude (Vpp × 1000) | `:w15={n}.` | `:w16={n}.` |
| Output (Ch1, Ch2) | `:w10=1,0.` | `:w10=0,1.` |

`__enter__`: Serial öffnen (115200 8N1), Output aus, Sinus setzen.
`__exit__`: Output aus, Serial schließen.

`MAX_AMPLITUDE_VPP = 9.5` als Modul-Konstante. `set_amplitude_vpp(vpp)` mit `vpp > 9.5` wirft `ValueError` (defensive guard; Pydantic-Validator fängt es normalerweise schon beim Laden).

### `FakeFunctionGenerator`

Hält den letzten gesetzten Zustand (sine, freq, amp, output) in Instanz-Variablen und loggt jeden Aufruf via `logger.bind(component="fg")`. Wird im Integration-Test inspiziert um die Aufrufreihenfolge zu prüfen.

### Factory

`build_function_generator(cfg, *, simulate) -> FunctionGenerator` in `devices/__init__.py`, analog zu den anderen Geräten.

### CLI

`--simulate-only` akzeptiert zusätzlich den Wert `function_generator`. Liste der erlaubten Werte in `cli.py` wird aktualisiert; unbekannte Werte werfen weiterhin `typer.BadParameter`.

### Kein eigener Worker

Der FG wird vom Orchestrator-Mainloop direkt vor der Stabilisierungspause aufgerufen. Befehle sind diskret (einmal pro Combo-Wechsel) — kein Thread nötig.

## Orchestrator-Loop

Pseudocode:

```
exp = ExperimentDirectory.create(...)
setup_logging(exp.root)
write experiment.json with status=RUNNING

with ExitStack() as stack:
    pump  = stack.enter_context(devices.pump)
    scope = stack.enter_context(devices.scope)
    fg    = stack.enter_context(devices.function_generator)
    stack.enter_context(devices.camera)
    scale_cm = stack.enter_context(devices.scale) if cfg.devices.scale.enabled else None

    if scale_cm is not None:
        initial_weight_g = scale_cm.read_weight_g()
        write ScaleRow(phase="initial", elapsed_s=0, weight_g=initial_weight_g)
                       in scale.csv
        re-write experiment.json with initial_weight_g

    fg.set_sine()
    fg.enable_output(False)

    combos = list(sweep.expand())
    # Erste Combo bekanntmachen, BEVOR Worker starten — sonst hat der erste
    # Worker-Tick keinen Step-Ordner zum Hineinschreiben.
    first = combos[0]
    state.update(first.combo_index, first.set_speed_rpm,
                 first.frequency_hz, first.amplitude_vpp)
    first_step_folder = exp.create_combo_folder(first)
    # PumpWorker/ScopeWorker bekommen das Experiment-Verzeichnis und beobachten
    # state.combo_index — sie öffnen ihren initialen Writer im ersten Step-Ordner.

    start PumpWorker, ScopeWorker (and ScaleWorker if enabled) as threads

    for combo in combos:
        if stop_event or error_event: break

        # erste Combo schon vor Worker-Start gesetzt; ab Combo 2 hier nachziehen
        if combo.combo_index > 1:
            state.update(combo.combo_index, combo.set_speed_rpm,
                         combo.frequency_hz, combo.amplitude_vpp)

        if combo.changed in ("initial", "rpm"):
            cmd_q.put(SetSpeedCommand(combo.set_speed_rpm))
        if combo.changed in ("initial", "rpm", "freq"):
            fg.set_frequency_hz(combo.frequency_hz)
        fg.set_amplitude_vpp(combo.amplitude_vpp)
        if combo.combo_index == 1:
            fg.enable_output(True)

        step_folder = first_step_folder if combo.combo_index == 1 \
                      else exp.create_combo_folder(combo)
        write initial step.json
        # PumpWorker/ScopeWorker beobachten state.combo_index und
        # rotieren ihre CSVs in step_folder (siehe Storage-Sektion)

        stabilization = timing.stabilization_for(combo.changed)
        cooperative_wait(stabilization)

        imaging_duration = max(0, combo.hold_s - stabilization)
        result = run_camera_capture(step_folder/"images", interval, imaging_duration, ...)

        finalize step.json
        append RunsRow to runs.csv

        if result.status == FAILED: abort experiment

    stop_event.set()
    join workers with timeout
```

Shutdown-Verhalten unverändert: Worker beenden über `stop_event`, joinen mit Timeout, im Fehlerfall ist `error_event` gesetzt und Status wird auf `FAILED` geschrieben.

## Storage-Layout

```
<base>/<UTC>__<experiment_id>/
  experiment.json
  experiment.log
  scale.csv
  runs.csv
  steps/
    combo_001_rpm0200_f20Hz_amp3.0V/
      step.json
      pump.csv
      oscilloscope.csv
      images/
        <UTC>.jpg
        ...
    combo_002_rpm0200_f20Hz_amp5.0V/
      ...
```

`scale.csv` bleibt im Experiment-Root, weil sie auch die initiale Messung vor dem ersten Step trägt.

### Ordnername

```python
def combo_folder_name(combo_index: int, rpm: int, freq_hz: float, amp_vpp: float) -> str:
    return f"combo_{combo_index:03d}_rpm{rpm:04d}_f{freq_hz:g}Hz_amp{amp_vpp:g}V"
```

`{:g}` formatiert `3.0 → "3"` und `9.5 → "9.5"`.

### CSV-Rotation in Workern

`PumpWorker` und `ScopeWorker` beobachten `state.combo_index`. Beim Wechsel:
1. Aktuelle Datei schließen.
2. Neuen Writer im neuen Step-Ordner öffnen (Header schreiben).
3. Mit dem Schreiben fortfahren.

Ein neuer Helper `RotatingCsvWriter` (in `storage.py`) kapselt das auf:

```python
class RotatingCsvWriter:
    def __init__(self, fieldnames: list[str]) -> None: ...
    def open_in(self, folder: Path, filename: str) -> None: ...
    def write(self, row: Any) -> None: ...                    # raises if not open
    def close(self) -> None: ...
```

`ExperimentDirectory` bekommt:
- `create_combo_folder(combo: SweepCombination) -> Path` — ersetzt das bisherige `create_step_folder`
- `append_runs_row(row: RunsRow) -> None` (öffnet die Datei lazy, schreibt Header beim ersten Aufruf)

Die bisherigen `open_pump_csv` / `open_oscilloscope_csv` (globale Writer) entfallen, weil pro Combo-Ordner geschrieben wird. `open_scale_csv` bleibt (global im Root).

### Row-Dataclasses

```python
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
    phase: str                        # "initial" | "sweep"
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
    step_folder: str                  # relativ zum Experiment-Root
    status: str
    n_captures: int
    failure_reason: str | None
```

`step.json` enthält zusätzlich `set_frequency_hz`, `set_amplitude_vpp`, `changed`, sowie die Pfade zu allen drei CSVs (relativ zum Step-Ordner).

`runs.csv` wird nach **jedem** abgeschlossenen Combo-Step geschrieben (per `append`), nicht erst am Ende — so überlebt der Report einen Mid-Sweep-Crash.

## Geräte-Skript-Verbesserungen (Scale)

`SartoriusScale.read_weight_g()` bleibt vom Vertrag her gleich, aber `__enter__` setzt jetzt Baudrate 1200, 7E1, mit `xonxoff=True` — wie im neuen `Script_read_Scale_v2.py`. Das stripping erlaubt jetzt auch das Format `+   12.345 g` (regex schon kompatibel — nur das Sign-Whitespace-Stripping aus dem Script übernehmen).

`ScaleConfig.interval_s` ist neu (Default 5). `ScaleWorker` liest `cfg.devices.scale.interval_s` statt `_SCALE_LOG_INTERVAL_S` zu hardcoden. Alle Worker-Zeilen erhalten `phase="sweep"`; die initiale Zeile mit `phase="initial"` schreibt der Orchestrator direkt vor dem Worker-Start.

## Hardware-Konstanten

In `devices/function_generator_psg9080.py` und im Config-Validator:

```python
MAX_AMPLITUDE_VPP: Final[float] = 9.5
```

In `function_generator_psg9080.py`: `set_amplitude_vpp(vpp)` wirft `ValueError(f"amplitude {vpp} Vpp exceeds hardware limit {MAX_AMPLITUDE_VPP}")` bei Überschreitung.

In `config.py`: Field-Validator auf `sweep.amplitudes_vpp` macht dasselbe als `ValidationError`.

## Test-Strategie

### Unit Tests

- `tests/unit/test_config.py` (erweitert):
  - valider Sweep parsed → Combos in richtiger Reihenfolge
  - `amplitudes_vpp` mit > 9.5 → `ValidationError`
  - leere Sweep-Liste → `ValidationError`
  - `speed_rpm > limits.max_speed_rpm` → `ValidationError`
  - `function_generator.channel ∉ {1, 2}` → `ValidationError`
- `tests/unit/test_sweep.py` (neu): `SweepConfig.expand()` produziert RPM-außen, `changed`-Flags korrekt
- `tests/unit/test_state.py` (erweitert): neue Felder im Snapshot
- `tests/unit/test_storage.py` (erweitert): `combo_folder_name`, `runs.csv`-Header und Row, `RotatingCsvWriter`

### Device Tests

- `tests/devices/test_function_generator_psg9080.py` (neu): mockt `serial.Serial`, prüft Befehlsformate, prüft `ValueError` bei Amplitude > 9.5, prüft Output-Off beim `__exit__`
- `tests/devices/test_function_generator_fake.py` (neu): State-Tracking
- `tests/devices/test_factory.py` (erweitert): `build_function_generator`, simulate-only-Pfad

### Worker Tests

- `tests/workers/test_pump_worker.py` und `test_scope_worker.py` (erweitert): CSV-Rotation beim `combo_index`-Wechsel
- `tests/workers/test_scale_worker.py` (erweitert): `phase="sweep"` in jeder Worker-Zeile; konfigurierbares Intervall

### Integration Test

- `tests/integration/test_orchestrator_end_to_end.py`: neues Mini-Sweep-YAML (2 RPM × 2 Freq × 2 Amp), läuft auf Fakes durch:
  - 8 Combo-Ordner in korrekter Reihenfolge
  - Pro Ordner `pump.csv`, `oscilloscope.csv`, `images/`
  - `scale.csv` im Root, erste Zeile `phase=initial`
  - `runs.csv` hat 8 Zeilen, Status `completed`
  - Fake-FG hat erwartete `(freq, amp)`-Sequenz erhalten
  - `experiment.json` enthält `initial_weight_g` und finalen Status

### CLI Test

- `tests/cli/test_cli.py`: `--simulate-only function_generator` akzeptiert; unbekannter Name wirft `typer.BadParameter`

## Edge Cases

| Situation | Verhalten |
|---|---|
| Ctrl-C zwischen Combos | letzter abgeschlossener Combo in `runs.csv`, Status `aborted` |
| FG-Crash mitten im Sweep | `error_event` gesetzt, Worker beenden, partielles `runs.csv`, Status `failed` |
| Waage liefert `None` für initiale Messung | `initial_weight_g=null` in `experiment.json`, Experiment läuft weiter |
| Sweep mit nur einer Combo (1×1×1) | funktioniert; `changed="initial"`, eine `runs.csv`-Zeile |
| Kamera failed in einer Combo | gesamtes Experiment bricht ab (`status=FAILED`), `runs.csv` enthält alle vorigen Combos plus die fehlgeschlagene |

## Out of Scope

- Globale `batch_report.csv` über mehrere Experimente hinweg (kommt mit dem DB-Cutover).
- Getrennte Stabilisierung pro RPM-Step (z.B. höhere RPM braucht länger) — heute alle RPM-Wechsel nutzen denselben Wert.
- Migrations-Skript für alte Experiment-YAMLs ins neue Schema — der Bruch ist akzeptiert.
