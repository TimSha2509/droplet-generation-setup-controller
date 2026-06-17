# Changelog

## Unreleased local changes - 2026-06-17

Compared with `origin/main` on GitHub, the local `HEAD` commit is not ahead or
behind. The changes below are local working-tree updates that are not currently
published on GitHub.

### Changed

- Updated `experiments/example_sweep_mini.yaml` for the
  `260612_Glycerol_90_IE` experiment:
  - Expanded sweep speeds from `1100` rpm to `1125`, `1175`, and `1225` rpm.
  - Expanded sweep frequencies to `5.0`, `5.5`, `6.0`, `6.5`, `7.0`, and
    `7.5` Hz.
  - Reduced per-step hold time from `150` seconds to `120` seconds.
- Adjusted `experiments/example_hpmc.yaml` sweep frequencies from `20` and
  `40` Hz to `6` and `10` Hz.

### Improved

- Made Sartorius scale readings more robust by flushing stale input, discarding
  the first line after a flush, and reading until a valid weight appears within
  a configurable read window.
- Tightened Sartorius weight parsing so only complete weight lines are accepted,
  preventing embedded numbers in status or garbage text from being parsed as
  valid weights.
- Added support for parsing signed scale readings with internal spacing.

### Tested

- Added Sartorius scale tests for:
  - Discarding stale first readings after input-buffer reset.
  - Skipping empty or invalid serial lines until a valid weight appears.
  - Rejecting lines with embedded numbers.
  - Parsing negative signed weight values.
  - Returning `None` when no valid reading arrives before the read window ends.

### Added

- Added untracked `DATA_TEST/` experiment output samples, including test
  experiment metadata, pump and oscilloscope CSVs, step JSON files, and sample
  image captures.
