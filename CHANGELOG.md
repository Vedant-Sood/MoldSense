# Changelog

## Unreleased

- Legacy imports keep their original time shape: rows are ordered by device UTC, uptime or row index instead of all sharing the import time, so plots and time ranges work.
- A failed legacy import is removed so it can be retried cleanly.
- A corrupted device-log chunk now fails only the download, not the live serial connection.
- Reject non-numeric `sample_interval_ms` and fall back to 1 s when it is missing.
- Jump-to-time honours a typed UTC offset.
- The earlier dashboard no longer writes duplicate archive copies of identical downloads.

## Repository import — 2026-10-26

- Import the research app and integrated ESP32 firmware into separate areas, retaining earlier firmware and standalone tools.
- Add setup, architecture, provenance, contribution guidelines, source packaging and CI checks.
- Separate restricted Bosch SDK files from redistributable source and add a hash-checked local installer.
- Update relative paths and release tooling; retain existing release-candidate versions and protocol.
- Harden telemetry parsing against oversized numeric values and boolean protocol versions.
- Keep historical sensor captures local, use synthetic reference tests, and make the legacy comparison optional.
- Make the Windows shortcut launcher portable without personal filesystem paths.

See `docs/VERIFICATION.md` for checks on this import. Original release notes remain under `docs/history/`.
