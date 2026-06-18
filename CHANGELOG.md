# Changelog

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
