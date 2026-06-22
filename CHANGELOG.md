# Changelog

## Unreleased - 2026-06-19

### Added

- Added displacement-mode sweeps with `sweep.displacements_um`, calibration-model
  loading, and resolved function-generator Vpp values.
- Added `droplet calibrate-displacement` to build frequency/voltage/displacement
  calibration JSON and CSV artifacts from oscilloscope readings.
- Added frequency-dependent max-voltage safety limits from Excel workbooks with
  amplifier gain confirmation before calibration and validation.
- Added optional pre-run displacement validation with terminal error reporting
  and warnings above the configured percent threshold.

### Changed

- Extended run metadata and CSV rows with target displacement alongside resolved
  Vpp values when displacement mode is active.
- Added `openpyxl` for reading `.xlsx` calibration limit workbooks.

## Unreleased - 2026-06-18

### Added

- Added deterministic sweep randomization with `sweep.random`, preserving stable
  combo folder names while executing the full cross-product in a seeded
  Fisher-Yates order.
- Added Arduino shutter triggering as an alternate camera backend while keeping
  DigiCamControl responsible for output-folder routing.
- Added camera timing support with `timing.wait_time_camera` so runs can pause
  between completed imaging steps before switching to the next combo.
- Added tests for randomized sweep order, recomputed stabilization change flags,
  Arduino trigger behavior, camera wait handling, and config validation.

### Changed

- Updated CLI dry-run output and generated config templates to show the sweep
  randomization setting.
- Updated orchestration so execution order is tracked independently from
  stable combo indices.
- Refreshed experiment examples and documentation for the current sweep schema,
  Arduino shutter configuration, and camera wait timing.

### Notes

- Local generated outputs such as `DATA_TEST/`, `Thumbs.db`, and exploratory
  plots are not part of this changelog entry.
