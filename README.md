# MoldSense

MoldSense combines an ESP32, a Bosch BME688 and a capacitive wall probe with a Windows research application. It records wall response, gas resistance and environmental conditions, then provides plots, session management, statistics and reproducible exports.

**Status:** research release candidate. Desktop **2.0.0-rc1**, integrated firmware **1.0.0-rc1**, serial protocol **1**. The firmware's 0–100 screening index is unvalidated; it is not a calibrated probability of mold. No validated mold classifier is included.

## Repository layout

| Path | Purpose |
| --- | --- |
| [desktop-app/](desktop-app/) | Python/Tkinter research app, original app under `--legacy`, assets, optional local references and tests |
| [firmware/esp32/MoldSense/](firmware/esp32/MoldSense/) | Main modular ESP32 sketch, configuration, production C++ modules, host tests and build tools |
| [firmware/legacy/](firmware/legacy/) | Earlier logger and capture firmware, with original sketch names |
| [firmware/tools/](firmware/tools/) | Standalone copper-comb test and one-shot AI-Studio capture programs |
| [docs/](docs/) | Architecture, setup, source provenance and current verification |
| [tools/](tools/) | Repository checks and reproducible source packaging |

## Run the desktop app

Install Python 3.11 or newer with Tk support. From the repository root on Windows:

```powershell
cd desktop-app
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_dashboard.py
```

The app can analyze saved sessions without an instrument. Live acquisition requires the integrated protocol-v1 firmware. Close Arduino Serial Monitor before connecting: only one program can own the serial port. To open the earlier dashboard, append `--legacy`.

Read the [desktop guide](desktop-app/README.md) for operation, exports and Windows builds. Application data is stored outside the source tree under the user's local application-data directory.

## Build the ESP32 firmware

The default board is the **classic ESP32 DOIT DevKit V1**, with BME688/OLED on GPIO21/22, copper-comb sensing on GPIO13, and switches on GPIO25/26. Verify actual wiring against the [firmware guide](firmware/esp32/MoldSense/README.md).

Install Arduino CLI and Espressif Arduino core **3.3.10**. The modified BSD-licensed BSEC wrapper and other redistributable dependencies are included. Bosch algorithm binaries, restricted headers and the default SDK configuration are installed locally from a separately obtained **BSEC 3.3.0.0** package:

```powershell
python firmware/esp32/MoldSense/tools/setup_bsec.py --source "C:\path\to\extracted-bsec-sdk"
python firmware/esp32/MoldSense/tools/setup_bsec.py --check
powershell -NoProfile -File firmware/esp32/MoldSense/tools/build.ps1
```

The setup tool verifies pinned SDK hashes before copying anything. It also accepts an existing complete MoldSense firmware folder. See [firmware setup](docs/FIRMWARE_SETUP.md) for the profile, dependencies and toolchain. Building does not upload or erase a device.

## Check the code

From the repository root with desktop dependencies installed:

```powershell
python -m unittest discover -s desktop-app/tests -p "test_*.py" -v
python firmware/esp32/MoldSense/tools/run_tests.py --compiler g++
python tools/check_repository.py
```

The C++ suite uses host mocks and needs a C++17 compiler; it does not require the proprietary SDK. CI runs desktop tests on Windows/Linux and the C++ suite on Linux. The [verification report](docs/VERIFICATION.md) records what was checked for this import and what needs hardware.

## Documentation

- [Architecture and compatibility](docs/ARCHITECTURE.md)
- [Desktop research workflow](desktop-app/RESEARCH_README.md)
- [Serial protocol](firmware/esp32/MoldSense/docs/PROTOCOL.md)
- [Database and analysis contract](desktop-app/docs/RESEARCH_DESIGN.md)
- [Scientific model and limitations](firmware/esp32/MoldSense/docs/SCIENCE.md)
- [Source import and historical versions](docs/SOURCE_PROVENANCE.md)
- [Contributing and commit guidelines](CONTRIBUTING.md)
- [Changes](CHANGELOG.md) and [third-party notices](THIRD_PARTY_NOTICES.md)

Project-authored code uses the existing [MIT license](LICENSE). Third-party code retains its own license; Bosch SDK components are not covered by this project's MIT license.
