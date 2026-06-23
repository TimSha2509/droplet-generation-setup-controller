# Experiments

Each experiment is one YAML file. Run it with:

```bash
uv run droplet run experiments/<your_file>.yaml
```

## Field Reference

| Field | Type | Unit | Description |
|---|---|---|---|
| `experiment_id` | string | - | Free-form identifier; appears in the output folder name. |
| `nozzle_id` | string | - | Free-form nozzle identifier. |
| `vibrometer.factor_um_per_v` | float > 0 | um/V | Calibration factor; multiplied by Vpp on CH1 to get peak-to-peak displacement. |
| `sweep.speeds_rpm` | list[int > 0] | rpm | Pump speeds used in the full cross-product. |
| `sweep.frequencies_hz` | list[float > 0] | Hz | Driving frequencies used in the full cross-product. |
| `sweep.amplitudes_vpp` | list[float > 0] | Vpp | Driving amplitudes used in the full cross-product. Use either this or `sweep.displacements_um`, not both. |
| `sweep.displacements_um` | list[float > 0] | um | Target peak-to-peak displacement values. Requires `displacement.model_path`; resolved to Vpp before the run. |
| `sweep.hold_s` | float > 0 | s | Total time spent at each combination. Imaging duration = `hold_s - stabilization_s`. |
| `sweep.random` | bool | - | Default `false`. If `true`, the full cross-product is executed in deterministic Fisher-Yates shuffled order using Python `random.Random(seed=0)`. Folder names keep the same `combo_NNN_rpm...` structure. |
| `timing.stabilization_rpm_change_s` | float >= 0 | s | Wait time after a pump speed change. |
| `timing.stabilization_freq_change_s` | float >= 0 | s | Wait time after a frequency-only change. |
| `timing.stabilization_amp_change_s` | float >= 0 | s | Wait time after an amplitude-only change. |
| `timing.image_interval_s` | float > 0 | s | Time between camera triggers. |
| `timing.camera_latency_tolerance_s` | float >= 0 | s | Extra wait after the planned imaging window before declaring the camera done. |
| `timing.wait_time_camera` | float >= 0 | s | Extra wait after a successful imaging step before moving to the next combo folder. Use this to let camera buffers clear before DigiCamControl switches folders. Default `0.0`. |
| `limits.max_speed_rpm` | int > 0 | rpm | Hard cap; sweep validation rejects speeds above this. |
| `displacement.model_path` | path or null | - | Calibration model JSON used for displacement-mode runs. Required when `sweep.displacements_um` is set. Calibration writes here when provided. |
| `displacement.max_voltage_table_path` | path or null | - | Excel workbook with `Frequency [Hz]` and `max. Voltage [V]` columns for calibration safety limits. |
| `displacement.amplifier_gain` | float > 0 | - | Default `2.0`. Workbook max voltages are divided by this gain before setting the function generator. |
| `displacement.calibration_start_hz` | float > 0 | Hz | Default `10.0`. First calibration frequency. |
| `displacement.calibration_stop_hz` | float > 0 | Hz | Default `120.0`. Last calibration frequency. |
| `displacement.calibration_step_hz` | float > 0 | Hz | Default `10.0`. Calibration frequency increment. |
| `displacement.voltage_steps` | int > 0 | - | Number of positive voltage steps from `max/N` through max at each frequency. |
| `displacement.measurement_s` | float > 0 | s | Default `10.0`. Measurement duration per calibration or validation point. |
| `displacement.scope_interval_s` | float > 0 | s | Default `0.5`. Time between oscilloscope measurements during calibration or validation. |
| `displacement.validation_enabled` | bool | - | If `true`, validate unique frequency/displacement pairs before running. |
| `displacement.validation_threshold_percent` | float > 0 | % | Default `10.0`. Warnings are printed when validation exceeds this percent error. |
| `devices.pump.port` | string | - | COM port on Windows or `/dev/tty...` on Linux/macOS. |
| `devices.pump.baudrate` | int > 0 | baud | Default `9600`. |
| `devices.oscilloscope.visa_resource` | string | - | VISA resource string from `droplet list-devices`. |
| `devices.oscilloscope.timeout_ms` | int > 0 | ms | SCPI query timeout. |
| `devices.camera.digicam_url` | string | - | DigiCamControl HTTP server URL. Default `http://localhost:5513`. |
| `devices.camera.request_timeout_s` | float > 0 | s | HTTP request timeout. |
| `devices.camera.trigger_backend` | `digicam` or `arduino` | - | Trigger source. `digicam` uses DigiCamControl for folder setting and shutter trigger. `arduino` uses DigiCamControl for folder setting and an Arduino serial shutter trigger. Default `digicam`. |
| `devices.camera.shutter_port` | string or null | - | Arduino serial port. Required when `trigger_backend: arduino`. |
| `devices.camera.shutter_baudrate` | int > 0 | baud | Arduino serial baudrate. Default `9600`. |
| `devices.camera.shutter_pulse_ms` | int > 0 | ms | Shutter pulse sent as `shoot <ms>`. Default `300`. |
| `devices.camera.shutter_read_timeout_s` | float > 0 | s | Timeout while waiting for the Arduino `OK shoot...` response. Default `2.0`. |
| `devices.function_generator.port` | string | - | Function generator serial port. |
| `devices.function_generator.channel` | `1` or `2` | - | Function generator output channel. Default `1`. |
| `devices.function_generator.baudrate` | int > 0 | baud | Default `115200`. |
| `devices.scale.enabled` | bool | - | If `false`, scale is not opened and `scale.csv` is not written. |
| `devices.scale.port` | string or null | - | Scale serial port. Required by real hardware when `enabled: true`. |
| `devices.scale.baudrate` | int > 0 | baud | Default `1200`. |
| `devices.scale.interval_s` | float > 0 | s | Time between scale reads. |
| `output.base_dir` | path | - | Parent directory for run outputs. The actual run folder is `<UTC-timestamp>__<experiment_id>` inside it. |

## Tips

* Run `uv run droplet validate <yaml>` after editing to catch typos and missing fields.
* Use `--simulate` for a dry run with fake hardware:
  ```bash
  uv run droplet run experiments/example_hpmc.yaml --simulate
  ```
* Use `--dry-run` to preview the exact sweep order before touching hardware.
* The shipped `example_hpmc.yaml` is a working reference. Copy and edit it for your runs.

## Arduino shutter trigger

DigiCamControl still handles image download and per-combo folder routing. To trigger
the camera through the Arduino remote-shutter sketch, set the camera trigger backend
and choose the Arduino COM port. Upload `docs/arduino_shutter_controller_v2.ino`
to the Arduino; the Python driver expects its `READY shutter-v2` protocol.

```yaml
timing:
  wait_time_camera: 5

devices:
  camera:
    digicam_url: "http://localhost:5513"
    trigger_backend: arduino
    shutter_port: COM7
    shutter_baudrate: 9600
    shutter_pulse_ms: 300
```

## Displacement mode

Use peak-to-peak displacement targets by replacing `sweep.amplitudes_vpp` with
`sweep.displacements_um` and pointing to a calibration model:

```yaml
sweep:
  speeds_rpm: [1125, 1175]
  frequencies_hz: [10, 20, 30]
  displacements_um: [1000, 1500]
  hold_s: 120

displacement:
  model_path: ./DATA/displacement_calibration.json
  max_voltage_table_path: ../VIBROMETER/CALIBRATION_V2/MaxDisplacement_init.xlsx
  amplifier_gain: 2.0
  voltage_steps: 5
  measurement_s: 10
  validation_enabled: true
  validation_threshold_percent: 10
```

Run `uv run droplet calibrate-displacement <yaml>` first to create the model,
then `uv run droplet run <yaml> --validate-displacement` to check the target
points before the actual experiment.
