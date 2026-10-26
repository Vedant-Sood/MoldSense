# MoldSense work list and release status

Updated 2026-09-14. Firmware **1.0.0-rc1**, desktop **2.0.0-rc1**, protocol **1**. This list covers both the original instrument-firmware request and the subsequent integrated research-desktop request. Development continued after the packaging checkpoint request; the package contains the final software changes and available verification, not an unfinished code dump.

## Completed software work

- [x] Inspect/preserve existing firmware, libraries, capture archives and desktop framework; record architecture decisions.
- [x] Modular new ESP32 project with centralized pins/settings and cooperative scheduling, touch-plate default, optional ADC front-end and extension interfaces.
- [x] BME688/BSEC3 integration, physical/virtual outputs, heater profile distinction, independent observation IDs, invalid/stale readings, retry and calibration diagnostics.
- [x] Independent CRC/version/identity-bound dual-slot wall and BSEC persistence, corruption fallback and read-back validation; baseline calibration cannot reset BSEC/model learning.
- [x] Robust local dry-reference calibration, statistics/progress, median/EMA filtering, relative wall index, debounced two-switch behavior and guarded commands.
- [x] Source-cited environmental risk explanation, observed-duration tracking, missing-evidence confidence, transparent contributions and unvalidated screening-index labeling.
- [x] Replaceable Bosch-model import interface with mapping/validation gates; NOT TRAINED when no validated model exists.
- [x] OLED scan/detail/calibration/fault flow, serial diagnostics, storage/heap/reset diagnostics and bounded optional logs.
- [x] Protocol-v1 telemetry, identity/configuration metadata, commands/ACKs, confirmation tokens, warnings and CRC/length-checked log downloads.
- [x] Existing Tkinter application extended with separate transport/database/statistics/plot/export modules; preserved legacy application under --legacy.
- [x] Automatic verified discovery/reconnect, session lifecycle, explicit acquisition versus visualization pause, elapsed time and data-quality/sequence events.
- [x] SQLite originals/derived columns/metadata, independent ground truth, experiments/samples/reused locations, annotations and legacy imports without invented missing data.
- [x] Primary wall/gas plots, current/session/rolling/control/range references, deviation, synchronized/normalized views, scatter and correlations, exact full-data distributions, chronological repeated-location plots and paginated raw table.
- [x] HTML research reports, standalone PNG/SVG figures, CSV/JSON/experiment exports and analysis metadata; debug view and presentation mode.
- [x] Real Arduino ESP32 compile: **465556 bytes flash, 47508 bytes global RAM**.
- [x] Production C++ host suite: **624 assertions passed**.
- [x] Desktop suite: **23 tests passed**; actual firmware serializer fixture consumed by desktop.
- [x] Offline eight-view UI smoke test, all five analysis types, synthetic report and figure inspection.
- [x] One-million-reading benchmark: all rows retained, table page 0.37 s, plot query 27.05 s, exact statistics 18.07 s.
- [x] Separate Windows portable build completed; packaged EXE offline self-test passed without serial access.
- [x] Hardware/wiring, protocol, database, science, calibration, model import, build/run and validation documentation.
- [x] Release packaging with per-file hashes, whole-archive SHA-256 and archive-content verification (see RELEASE_VERIFICATION.json).

## Remaining production qualification — requires hardware or experimental evidence

These items cannot be completed by compiling code or generating synthetic data. No claim is made that they have passed.

1. **Hardware identity and backup:** verify actual classic ESP32/flash map, GPIO wiring, plate electrode arrangement, addresses and voltage levels. Before an explicitly authorized upload, save/read-back-verify full flash and all files under old_data. No device was flashed by this implementation.
2. **Probe characterization:** verify wet-response direction, insulation/contact/cable sensitivity, range/saturation limits, dry repeatability, noise and material-specific normalization. A bare floating touch plate cannot conclusively distinguish disconnection from a plausible measurement; reliable contact/open-wire detection needs appropriate hardware or a separate check.
3. **Live integration:** test BME/OLED unplug/replug, bus faults, switch bounce/boot state, actual baseline save/cancel/power-cycle, BSEC state restoration, USB resets/COM changes/multiple devices, command ACKs and actual log download integrity.
4. **Long-run/storage qualification:** 72-hour stationary soak; observe heap/reset reason, sample loss, flash-write intervals, full disk/filesystem, brownouts and interrupted writes on a sacrificial unit. Verify active SQLite backup/recovery and app behavior on the actual Windows/USB installation.
5. **Independent scientific experiments:** dry/wet material controls, sustained RH and brief spikes, unrelated VOCs, repeat locations/materials/days and blinded ground truth. Establish detection limits/confounders and calibration uncertainty.
6. **Validated mold model:** collect appropriate full heater-profile Bosch raw captures, train outside this application, verify class mapping and independent held-out performance, document validation, then deliberately import a compatible model. There is no mold model in the current package.
7. **Index validation:** the fusion weights, normalization and risk bands need outcome-labelled validation. A validated VOC classifier alone does not convert the combined screening index into a calibrated probability of hidden mold.
8. **External distribution:** review Bosch binary redistribution/license requirements; perform a clean-machine Windows test and decide whether signed executables/installers are needed. The current portable build was tested on the development machine and adds no Startup registration.

## Optional future work (not required for the verified Arduino release)

- Compile/qualify the supplied alternative PlatformIO environment; the release binary is verified using Arduino core 3.3.10.
- Hardware port to ESP32-S3, multiple probes, actual wall-surface temperature, RTC/SD, wireless interfaces or cloud. Interfaces are prepared; these features are deliberately not implemented.
- Add formal inferential experiment workflows only after an independent-replicate design is specified. CI/effect-size helpers exist; arbitrary time-series rows are not treated as independent trials.
- Improve full-history plot/statistics latency beyond the measured million-row performance if larger studies require it; current heavy queries run outside acquisition/UI threads.

## Starting points

- Firmware guide: `MoldSense/README.md`; edit `MoldSense/Config.h` for hardware.
- Desktop guide: `moldsenseusercodev1/RESEARCH_README.md`.
- Source launcher: `moldsenseusercodev1/run_dashboard.py`.
- Portable executable: `Windows/MoldSense-Research-2.0.0-rc1/MoldSense-Research-2.0.0-rc1.exe` inside the archive. Keep the adjacent `_internal` directory.
- Source science/bench details: `MoldSense/docs/SCIENCE.md` and `VALIDATION.md`.
- Database/analysis details: `moldsenseusercodev1/docs/RESEARCH_DESIGN.md`.
- Verification evidence: `MoldSense/build` and `outputs/moldsense_research_qa`.

LOW means a low current screening score, not confirmed absence of mold. Uptime is not calendar time. Raw gas resistance alone has no mold interpretation.
