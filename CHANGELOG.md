# Changelog

## Unreleased - 2026-06-23

Compared with `origin/codex/changelog-controller-updates`.

### Added

- Added the `docs/arduino_shutter_controller_v2.ino` sketch with a nonce-based
  serial protocol (`READY shutter-v2`, `ping <id>`, `press <id>`,
  `release <id>`, and `shoot <ms> <id>`).
- Added a runtime-checkable `ContinuousCamera` protocol so camera backends can
  expose press/release capture windows without changing DigiCamControl or fake
  camera behavior.
- Added CLI validation that rejects fully real runs when the Arduino shutter
  port is also assigned to another real serial device such as the pump, function
  generator, or scale.
- Added tests for Arduino startup handshakes, nonce-matched responses, stale
  response handling, retry exhaustion, continuous press/release capture, and COM
  port conflict validation.

### Changed

- Reworked the Arduino camera backend to require the v2 startup handshake,
  clear stale serial input, use command IDs, retry commands up to five total
  attempts, and ignore stale responses from earlier command IDs.
- Changed Arduino-backed imaging from repeated `shoot` commands to one
  `press` command at the start of the imaging window and one `release` command
  at the end.
- Updated camera capture orchestration to use continuous press/release mode only
  for cameras that implement `ContinuousCamera`; DigiCamControl and fake cameras
  still use the existing interval-based trigger loop.
- Updated Arduino shutter documentation and experiment examples to point to the
  v2 sketch and Arduino trigger configuration.

### Notes

- Local generated outputs such as `DATA_TEST/`, `Thumbs.db`, exploratory plots,
  and personal experiment files are not part of this changelog entry.

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
