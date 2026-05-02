# Experiments

Each experiment is one YAML file. Run it with:

```bash
uv run droplet run experiments/<your_file>.yaml
```

## Field reference

| Field | Type | Unit | Description |
|---|---|---|---|
| `experiment_id` | string | — | Free-form identifier; appears in output folder name. |
| `nozzle_id` | string | — | Free-form nozzle identifier. |
| `actuation.frequency_hz` | float > 0 | Hz | Driving frequency the actuator is set to. |
| `actuation.voltage_v` | float > 0 | V | Driving voltage. |
| `actuation.vibrometer_factor_um_per_v` | float > 0 | µm/V | Calibration factor; multiplied by Vpp on CH1 to get peak-to-peak displacement. |
| `ramp[i].speed_rpm` | int > 0 | rpm | Pump speed for this step. |
| `ramp[i].hold_s` | float > 0 | s | Total time spent at this speed. Imaging duration = `hold_s - timing.stabilization_s`. |
| `timing.stabilization_s` | float ≥ 0 | s | Wait time after speed change before imaging starts. |
| `timing.image_interval_s` | float > 0 | s | Time between camera triggers. |
| `timing.camera_latency_tolerance_s` | float ≥ 0 | s | Extra wait after the planned imaging window before declaring the camera done. |
| `limits.max_speed_rpm` | int > 0 | rpm | Hard cap; ramp validation rejects steps exceeding this. |
| `devices.pump.port` | string | — | COM port (Windows) or `/dev/tty…` (Linux/macOS). |
| `devices.pump.baudrate` | int > 0 | baud | Default `9600`. |
| `devices.oscilloscope.visa_resource` | string | — | VISA resource string from `droplet list-devices`. |
| `devices.oscilloscope.timeout_ms` | int > 0 | ms | SCPI query timeout. |
| `devices.camera.digicam_url` | string | — | DigiCamControl HTTP server URL (default `http://localhost:5513`). |
| `devices.camera.request_timeout_s` | float > 0 | s | HTTP request timeout. |
| `devices.scale.enabled` | bool | — | If `false`, scale is not opened and `scale.csv` is not written. |
| `devices.scale.port` | string\|null | — | Required when `enabled: true`. |
| `devices.scale.baudrate` | int > 0 | baud | Default `9600`. |
| `output.base_dir` | path | — | Parent directory for run outputs. The actual run folder is `<UTC-timestamp>__<experiment_id>` inside it. |

## Tips

* Run `uv run droplet validate <yaml>` after editing to catch typos and missing fields.
* Use `--simulate` for a dry-run with fake hardware:
  ```bash
  uv run droplet run experiments/example_hpmc.yaml --simulate
  ```
* The shipped `example_hpmc.yaml` is a working reference — copy and edit it for your runs.
