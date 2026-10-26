# MoldSense research workspace 2.0.0-rc1

The default source launcher now opens the integrated research application. It uses the existing Tkinter framework, pyserial and SQLite, with NumPy/SciPy statistics and Matplotlib scientific figures. Wall response and BME688 gas resistance are the primary signals. Firmware screening predictions remain secondary evidence. No trained mold model, physical experiment, hardware validation or new firmware upload was performed by this implementation.

**Start here:** [architecture assessment](ARCHITECTURE_ASSESSMENT.md), [data/analysis design](docs/RESEARCH_DESIGN.md), [validation](docs/RESEARCH_VALIDATION.md), and [ESP32 protocol](../firmware/esp32/MoldSense/docs/PROTOCOL.md). Existing packaged 1.1 desktop executables are the older application; source changes do not update installed EXEs automatically. Existing firmware/captures and the old archive are preserved. `--legacy` opens the earlier application.

## Run on Windows

From this directory, with Python 3.11+ installed:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_dashboard.py
```

The existing `start_dashboard.ps1` launcher uses this same source entry point and prefers `.venv`. It does not change Windows Startup registration. To open the old application explicitly:

```powershell
.\.venv\Scripts\python.exe run_dashboard.py --legacy
```

For a portable EXE build use `build_research.ps1`; it has a separate research output name and does not replace older installers. The exact environment validated here is recorded in `requirements-validated.txt`; `requirements.txt` gives supported dependency bounds. No cloud, login, ML download or paid service is required.

Connect an ESP32 running `../firmware/esp32/MoldSense` protocol 1. The old logger/capture firmware is not automatically considered compatible; use the legacy view for its archive workflows. Do not flash a working device until its data and full flash have been backed up and the new firmware has passed the bench procedure.

## First experiment

1. Open the app; discovery checks USB serial candidates and verifies MoldSense identity/protocol. With several matching units choose the correct device. Device health shows ID, firmware, model, state and communication diagnostics.
2. Inspect Calibrations and Device. `VOC MODEL: NOT TRAINED` is expected for this delivery. It does not invalidate physical gas measurements; it means there is no VOC mold-classification evidence.
3. Create a session with experiment, sample, location, room, material, ground truth and notes. Reuse the same saved location for repeat visits. Leave ground truth UNKNOWN for blinded samples. Labels may be customized; `CONFIRMED_MOLD` requires independent evidence entered by the researcher, never the firmware score.
4. Place the insulated plate on a representative dry reference. Select **Calibrate wall**, deliberately confirm, remain stationary for 60 s, and inspect success/accepted samples/dispersion. BSEC state and the model are untouched. Physical baseline switch works independently of the app.
5. Start recording. The app archives original frames and readings before notifying the chart. Keep placement, cable geometry and pressure consistent. An annotation records probe moves, reference changes and observations.
6. **Pause view** freezes visualization while acquisition continues. **Pause acquisition** stops new reading rows but keeps incoming original packets and events for audit. **Resume acquisition** creates a visible interruption boundary. **Stop session** closes recording and generates a summary/report. A stopped session cannot be resumed; create a new session.
7. When moving to another wall position, use **New wall position** in Device to reset firmware exposure history, then create the appropriate session. A short hand scan cannot measure 24 hours of exposure. The baseline and material identity should remain appropriate for the new location.

## Views and analysis

- **Live:** large wall/gas values, synchronized time axes, raw/filtered/index selector, dry baseline, exact session mean, 30-observation rolling mean, optional control/range mean and relative wall alert. Gas card and plot use the selected heater step. The viewport is reduced for rendering; stored readings are not reduced.
- **Experiments:** sessions, independently assigned labels, repeated locations and legacy imports. Select several rows before Analysis to compare groups. Labels never derive from a model score.
- **Analysis:** paired scatter, normalized wall/gas traces, full-data histograms/box plots, repeated-session means, descriptive statistics, Pearson and Spearman correlation. Select a control and heater step; Analyze selection applies current quality settings. The longitudinal view sorts by session start date and separates locations/materials into distinct traces; match experimental conditions before interpreting a trend.
- **Data:** sortable/searchable table, 250-row pages, visible-column selection, UTC jump, raw row inspection and row/range export. Double-click a chart point to inspect its underlying row. Hover details report receive time, uptime, raw/filtered values, baseline and deviations.
- **Calibrations:** current baseline, statistics and progress. Cancellation or failed calibration leaves the old baseline valid; that is not a successful new calibration.
- **Device:** identity, compatibility, BSEC accuracy/state, model, storage and sensors; guarded reset/download controls and a raw-protocol debug toggle.
- **Reports:** original/processed CSV, complete session/experiment JSON, HTML reports and standalone PNG/SVG figures.
- **Settings:** telemetry interval and versioned analysis policy. Firmware owns physical filtering and risk calculations. The app does not overwrite a firmware value with a recalculated estimate.

Matplotlib's toolbar supplies pan/zoom/home. Select range freezes the view and allows dragging a time interval; range statistics and selected-variable exports use that interval. Custom time ranges accept two ISO timestamps in UTC. Presentation hides research controls and uses the main figures; Esc restores controls. Original collection continues.

Correlations are descriptive and cannot prove mold or causation. Serially correlated readings are not independent replicates. No misleading per-reading confidence interval is shown. Independent-session CI/effect-size helpers are available for a validated experimental design, not automatically applied to arbitrary selected sessions. See the design guide for every formula and exclusion rule.

## Data and exports

By default the new database is `%LOCALAPPDATA%/MoldSense/UserDashboard/research.sqlite3`. The old `moldsense.db` and archived capture files are unchanged. New data is local. Back up the database with its `-wal`/`-shm` files while active, or close the app and copy the database. Do not copy only the main SQLite file while writes are active.

Raw JSON packets are authoritative. Reading columns index useful fields; derived rolling values are separately named. CSV/JSON exports include sample ground truth, device/boot/firmware/model/baseline/analysis identity and timestamps. Sidecars contain metadata and SHA-256. Original malformed frames, duplicate packets, reconnects and baseline events remain auditable in complete JSON. CSV alone is not a complete protocol archive.

Choose a **stopped** session for a publication export so all exported tables describe a stable record. Active exports are bounded at an ID watermark to prevent unbounded growth, but independent tables can capture slightly different endpoints. Exports never delete the database. Selected rows export is a small convenience JSON; use complete session exports for a full provenance package.

Reports include wall/gas figures, reference lines, statistics, correlations, environment, annotations, labels and configuration metadata. Print HTML to PDF if needed. PNG/SVG exports are independent figures, not screenshots of the UI; preserve their metadata sidecars with the manuscript files. The QA report under `../outputs/moldsense_research_qa` is prominently SYNTHETIC and must not be treated as experimental evidence.

Device log download validates chunk CRC, contiguous offsets and total length, then writes a SHA-256 sidecar under `device_logs`. Interrupted downloads retain `.partial`; a success ACK alone does not certify a download.

## Recovery and limits

A disconnected instrument preserves the session and is searched by physical ID, including changed COM ports. Reboots have separate sequence domains. Charts show gaps rather than interpolating missing observations. Restarting the app marks previously active sessions interrupted; select and Resume to continue deliberately. No synthetic readings replace missing sensors or downtime.

The million-row benchmark retained every row, paged 250 rows in 0.37 s, produced 2086 plot points in 27.05 s, and calculated exact statistics in 18.07 s on this machine. Heavy work runs away from the UI and serial collector; full-history queries are not instantaneous. Exact quantiles/correlations use compact arrays proportional to the selected dataset. Native SQLite may still be limited by disk/antivirus/cloud synchronization. Keep the live database on local storage, not a synchronized capture folder.

The copper-comb plate measures a material/geometry-dependent electrical response, not universal moisture percent. A floating/disconnected electrode can look electrically plausible. No wall-surface thermometer is present, so condensation is unavailable, not inferred from invented surface temperature. The combined index is a configurable unvalidated screening score; outcome-labelled independent validation is still required.
