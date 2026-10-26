# Changelog

## Repository import — 2026-10-26

- Import the research app and integrated ESP32 firmware into separate areas, retaining earlier firmware and standalone tools.
- Add setup, architecture, provenance, contribution guidelines, source packaging and CI checks.
- Separate restricted Bosch SDK files from redistributable source and add a hash-checked local installer.
- Update relative paths and release tooling; retain existing release-candidate versions and protocol.
- Harden telemetry parsing against oversized numeric values and boolean protocol versions.

See `docs/VERIFICATION.md` for checks on this import. Original release notes remain under `docs/history/`.

- Keep historical sensor captures local, use synthetic reference tests, and make the legacy comparison optional.
- Make the Windows shortcut launcher portable without personal filesystem paths.
