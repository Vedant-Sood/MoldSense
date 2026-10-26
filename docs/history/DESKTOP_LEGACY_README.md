> **Research update:** The source launcher now opens **MoldSense Research 2.0.0-rc1**. See [RESEARCH_README.md](RESEARCH_README.md) for the new protocol, experiment workflow, analyses, exports and tests. The older 1.1 packaged executables and their instructions below remain unchanged. Use `--legacy` for the earlier source UI.

# MoldSense User Dashboard 1.1

MoldSense is a customer-facing Windows application for exploring ESP32/BME688 environmental recordings. Data collection remains controlled by the physical buttons on the device. The dashboard imports, verifies, stores, compares, graphs, and explains the recordings without exposing firmware initialization, training, or engineering controls.

## Install the application

Open [`release/MoldSense-Setup-1.1.0.exe`](release/MoldSense-Setup-1.1.0.exe) and accept the installation prompt. Setup installs MoldSense for the current Windows user and creates:

- a desktop shortcut;
- a Start Menu shortcut;
- an Apps & Features uninstaller.

It does **not** add MoldSense to Windows Startup. Uninstalling preserves archived sensor logs under `%LOCALAPPDATA%\MoldSense\UserDashboard`.

For use without installation, open [`release/MoldSense-Portable.exe`](release/MoldSense-Portable.exe). Python and Arduino IDE are not required for either release.

The binaries are not code-signed, so Windows SmartScreen may show an unrecognized-app warning. SHA-256 checksums are recorded in [`release/SHA256SUMS.txt`](release/SHA256SUMS.txt).

## Customer workflow

1. Use the physical device buttons to collect a baseline or test.
2. Plug MoldSense into the computer and wait for the green **Connected** status.
3. Select **Import from device**. Every recognized log is downloaded twice and verified before the app requests deletion.
4. Use an ordinary room recording as the baseline.
5. Open **Explore data** to compare any two recordings.
6. Review marked periods under **Deviations** and confirm persistent findings with inspection or professional testing.

The dashboard also works without an ESP. Cap 1, the 216-row Cap 1 dataset tailored to Cap 2, and Cap 2 are bundled for immediate exploration.

## Application features

### Overview

- Customer-friendly health summary with Normal, Watch, High, or No Baseline states.
- Reading, dataset, deviation, and baseline counts.
- Recent-test library.
- Tailored Cap 1 versus Cap 2 summary and one-click overlay.

### Explore data

- Independent primary and comparison selectors.
- Compare bundled references, imported device logs, or manually added previous tests.
- IAQ, temperature, humidity, pressure, and gas-resistance signals.
- Optional two-color overlay and independent mean lines.
- Logarithmic gas-resistance view so every heater step remains readable.
- Hover inspection, normalized progress axis, baseline selection, and CSV export.

### Deviations

- Robust baseline deviations grouped into time periods.
- High, Moderate, and Reference filters.
- Full risk interpretation and suggested next action.
- Overall Cap-profile comparison plus all ten heater-step differences.

### Data library

- Searchable imported-test and bundled-reference catalog.
- Direct import of existing `.csv` and `.bmerawdata` files.
- Reading counts, mode information, timestamps, and checksum status.
- Compare or export selected data.

### Safety and privacy

- Local-only operation; no account, cloud service, or internet connection is needed after installation.
- Double-download verification and SHA-256 archive manifests.
- BSEC state, model, and configuration files are never eligible for deletion.
- No initialization, capture-training, model-upload, or mode-change controls.

MoldSense detects environmental patterns. It cannot prove mold is present, identify a mold species or chemical, determine medical safety, or replace inspection and professional testing. Low IAQ accuracy reduces confidence and is stated in warnings.

## Device log clearing

Existing firmware can download logs but protects them from its generic delete command. The optional [`firmware_extension/SAFE_LOG_DELETE.patch`](firmware_extension/SAFE_LOG_DELETE.patch) adds a narrow `LOG_DELETE` command for recognized logs only. This is a one-time firmware installation; it is not needed to open, analyze, archive, or compare data.

## Build from source

The source version uses Python 3.11 or newer, Tkinter, SQLite, and pyserial. From PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_windows.ps1
```

To run the source version manually:

```powershell
.\start_dashboard.ps1
```

To rebuild the portable executable and setup package:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
```

The build uses PyInstaller for the application and the built-in Windows IExpress compiler for the per-user setup package. Build outputs are placed under `release`.

## Verify

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Get-FileHash .\release\MoldSense-Portable.exe -Algorithm SHA256
Get-FileHash .\release\MoldSense-Setup-1.1.0.exe -Algorithm SHA256
```

Automated coverage validates baseline/deviation calculations, pressure normalization, protected deletion paths, checksum archives, and all three bundled capture datasets.
