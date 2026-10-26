# MoldSense firmware — integrated research instrument

Version 1.0.0-rc1. **Compiled and software-tested release candidate, not a field-qualified production release.** No hardware was flashed for this implementation. Physical validation and outcome-labelled model validation remain release gates. The displayed Mold Probability Index is an **unvalidated 0–100 screening index**, not a calibrated probability of mold presence, hidden-wall diagnosis, or a health/safety certificate.

Start with [scientific model](docs/SCIENCE.md), [validation and release gates](docs/VALIDATION.md), and [protocol](docs/PROTOCOL.md). The companion research desktop source is in `../../../desktop-app`; it retains the earlier Tkinter application under `--legacy`.

## Hardware configuration and assumptions

Edit **Config.h** at the top of this project. Default target: classic ESP32 DOIT DevKit V1, 3.3 V logic. The user confirmed a bare copper-comb touch plate. The active backend is `Esp32Touch`; an analog-voltage backend is also implemented but disabled.

| Connection | Default | Notes |
|---|---:|---|
| I2C SDA | GPIO21 | BME688 and OLED share bus |
| I2C SCL | GPIO22 | 100 kHz, 25 ms bus timeout |
| BME688 | 0x76 | Set to 0x77 for a board wired that way |
| OLED SSD1306 128×64 | 0x3C | Configure 0x3D if required; 3.3 V-compatible module |
| Baseline slide switch | GPIO25 | Switch connects pin to GND when ON; internal pull-up |
| Detail/scan switch | GPIO26 | ON to GND = DETAIL; OFF = SCAN |
| Copper-comb sensing electrode | GPIO13 / T4 | Classic ESP32 touch units; NOT picofarads |
| Analog front-end (inactive) | GPIO34 / ADC1 | Only conditioned, bounded voltage; not a bare capacitor |
| All returns | GND | Common reference; verify actual module labels |

For an interdigitated two-electrode plate, the sensing electrode is on the touch pin and the other electrode is the reference/ground. Verify that this matches the plate's existing circuit. Keep electrodes insulated from conductive/wet building surfaces; characterize the same protective layer, cable routing, contact pressure and stand-off used during calibration. Touch counts typically **decrease** as capacitance increases on classic ESP32. This response direction is configurable. An open/floating plate can still give a plausible touch value; firmware cannot prove electrical connection or wall contact. ADC open-circuit detection likewise needs a biased front-end with a known fault range. Do not connect a 5 V output to an ESP32 input.

No wall-surface temperature sensor is fitted. Dew point is calculated from air conditions; actual wall surface RH and condensation risk remain unavailable. The `SurfaceReading` interface allows a future measured input without changing the risk engine.

## Layout and dependencies

```
MoldSense.ino              setup()/loop() only
Config.h                  hardware and tunable settings
src/App.cpp               cooperative scheduling and commands
src/Core/                 value types, CRC, math, switches
src/Sensors/              BME/BSEC manager; wall front-end
src/Calibration/          independent robust wall calibration
src/Analysis/             classifier validity; risk/exposure model
src/Models/               Bosch default IAQ config; optional trained export
src/Storage/              dual-slot NVS and bounded LittleFS logs
src/UI/                   OLED, bounded console, NDJSON serializer
vendor/                   pinned sources; BSEC SDK installed separately
 tools/                   build, model import, native C++ tests
 tests/                   replay tests and hardware mocks
```

Redistributable dependencies are bundled in `vendor`: project-specific BSEC3 Arduino wrapper 3.3.0; Bosch BME68x Sensor library **1.3.40408**; Adafruit SSD1306 **2.5.17**; Adafruit GFX **1.12.6**; Adafruit BusIO (see its `library.properties`). ESP32 Arduino core supplies Wire, Preferences and LittleFS. The verified core is **3.3.10**. This is a local adaptation of Bosch's wrapper, not a claim that Bosch certifies this application. Preserve vendor license files. Install the restricted BSEC **3.3.0.0** headers, ESP32 binary and default profile locally using [the SDK setup guide](../../../docs/FIRMWARE_SETUP.md). They are excluded from Git.

The project uses BSEC3 because the existing workspace contains this compatible library/configuration family. It does not silently restore the earlier BSEC2 blob. The private wrapper fixes the 32-bit uptime-wrap increment, avoids copying the callback instance, and preserves pressure in Pa as required by the bundled BSEC API headers. Existing workspace libraries are unchanged.

## Build and flash

Arduino IDE: open `MoldSense.ino`, select **DOIT ESP32 DEVKIT V1**, install ESP32 core 3.3.10, and install the supplied vendor libraries into the sketchbook's libraries directory. Use the supplied BSEC3 wrapper rather than another similarly named installation.

Reproducible Arduino CLI build from the repository root:

```powershell
powershell -NoProfile -File firmware/esp32/MoldSense/tools/build.ps1
```

On another PC use an installed `arduino-cli`, or `tools/build.ps1 -ArduinoCli <path>`. Arduino recursively compiles `src`; do not move the module directories outside it. The supplied `platformio.ini` is an alternate project configuration, but its different Arduino core has **not** been validated by this run. The Arduino build is the verified release path.

**Before a future upload:** verify board variant, port, wiring, flash size and partition map; back up the existing full flash and all files to `old_data`, check sizes and SHA-256, and retain a rollback image. Existing BSEC2/3 and capture files are never migration inputs automatically. Select upload only when ready; no erase/format/upload command is part of the build script. A manual Arduino CLI upload after that gate is `arduino-cli upload --fqbn esp32:esp32:esp32doit-devkit-v1 --port COMx --input-dir firmware/esp32/MoldSense/build firmware/esp32/MoldSense`. Replace COMx with the verified device. Do not upload to an ESP32-S3 using this binary.

## Operating and calibrating

1. Power the device, inspect `STATUS`, `DEVICE_INFO`, `MODEL_INFO`, and `GET_BASELINE`. Allow the BME688 to settle; IAQ accuracy/run-in are reported, not fabricated.
2. Hold the plate on a representative dry reference of the **same material, geometry and mounting** as subsequent measurements. Dryness is an operator assumption; the instrument does not certify it.
3. With the baseline switch first OFF, slide it ON and hold for two seconds. If it was ON at boot it must be returned OFF before it can start calibration. Alternatively use the app's Calibrate wall action or `START_BASELINE` followed by the returned one-use `CONFIRM` token.
4. Keep stationary for 60 s. At least 80% of scheduled samples must be usable. Median/MAD rejection, standard deviation, drift, RH and temperature stability gates reject unstable references. Progress is shown on OLED and in the application.
5. A baseline replaces the active baseline only after a verified persistent write. Failure/cancellation preserves the old baseline. Starting calibration never calls BSEC reset, `setState`, `setConfig`, or training.
6. Return baseline switch OFF. Use the other switch for Scan/Detail. Start a **NEW_SITE** when moving to a new wall position; duration means time observed at the present position, not the age of a wall's dampness.

The baseline contains accepted/total count, mean, median, sample SD, confidence, local air temperature/RH/dew point and a zero-origin relative moisture reference. No automatic baseline tracking is performed: automatic adaptation could erase a slow wetting event. Updating `wallSetupId` invalidates references after hardware/material changes.

## Persistence and fault recovery

Wall state uses NVS namespace `ms_wall_v1`; BSEC uses `ms_bsec_v1`. Each has independent a/b records with schema, sequence, identity, payload length and CRC32. Writes target the older/inactive slot, then read back and validate it. Loading chooses the newest intact compatible record and can fall back to the other slot. The calibration namespaces and earlier files are never erased.

BSEC fingerprint includes configuration bytes, library version, physical BME unique ID and temperature offset. Configuration is loaded **before state**, because state must be interpreted by the matching profile. Mismatched/corrupt state is reported and rejected. The first calibrated save is attempted after 10 minutes and subsequent saves at six-hour intervals, with a one-minute retry interval after write failure; power loss can discard learning since the last checkpoint. An OLED allocation occurs once; main data buffers are fixed size. I2C/storage/vendor calls still have bounded latency and require the bench soak test.

BME faults/staleness invalidate evidence and schedule retry every 10 s; OLED retries independently. Wall ranges/noise reject unusable samples and recover after a stable window. Missing sensors are not zero-risk readings: score may be UNKNOWN and confidence falls. Exposure memory is **session RAM**, resets on boot/new-site and never counts unobserved power-off time. These are observable screening durations, not a biological growth clock.

Optional device CSV logging is disabled by default (`loggingEnabled`). It uses a 60 s interval, 3 KB buffer, five-minute flush, 256 KB maximum and stops on full instead of deleting history. LittleFS is never formatted automatically. A partial final CSV row after power loss is possible; raw desktop logging is the preferred research record. Only `/ms_log.csv` is eligible for CLEAR_LOG. `FORMAT_LOGS` is guarded and only offered when mounting failed; it formats the entire LittleFS partition and must not be used until all existing data is backed up.

## OLED and serial

Scan emphasizes index, risk, wall index, RH and degraded/model status. Detail cycles every five seconds through environment, wall, BME AI, diagnostics and contributions. Missing values display unavailable (`nan` in small diagnostic fields); the main index is `--` when unavailable. Frame content is compared before an OLED transfer. Baseline calibration temporarily shows progress. Software cannot verify a physically correct OLED image from I2C ACK alone.

NDJSON commands and acknowledgements are documented in [PROTOCOL.md](docs/PROTOCOL.md). Human diagnostics remain available as `EXPLAIN`, `BASELINE`, `SENSOR_INFO`, `CALIBRATE`, `CANCEL`, and legacy `DUMP`. Every guarded operation requires a one-use token except the deliberate physical switch gesture. Boot/status human lines are diagnostic text, not reading packets; the desktop retains them as raw events.

## Trained Bosch model

No mold model is supplied or enabled. `VOC MODEL: NOT TRAINED` is expected. BSEC IAQ mode supplies IAQ/static IAQ/eCO2/bVOC and run-in/accuracy. A validated classification configuration uses the **AI scan profile instead**; IAQ outputs unavailable in that profile remain null. One physical heater cannot simultaneously execute incompatible IAQ and scan schedules.

Collect labelled full heater-profile raw scans with the existing dedicated capture firmware, including independent dry/damp controls, unrelated VOC challenges, multiple materials, sensors and days. Ordinary telemetry CSV is **not** an AI-Studio `.bmerawdata` training capture. Train/export a BME688 BSEC **3.3.0.0-compatible** classification configuration (2–4 classes), and verify its zero-based class mapping. Do not relabel the historical Chai classifier as mold.

```powershell
python firmware/esp32/MoldSense/tools/import_model.py exported_model.c --name WallStudy_v1 --mold-class 1 --class-count 2 --bsec-version 3.3.0.0
```

This imports the data into `src/Models/MoldModelData.h` as **unvalidated**. To enable inference for a independently evaluated mold model, explicitly use `--validated --validation-report report.json --validation-quality 0.85` with a defensible quality metric and held-out report; 0.85 is syntax illustration, not a measured result. Record sensitivity/specificity, false positives, calibration and domain of applicability. The tool hashes bytes/report and refuses silent replacement unless `--replace` is supplied. Importing a report does not mechanically certify its scientific quality. Bosch still checks binary compatibility at initialization. Replace/rebuild to change models; baseline calibration never replaces one.
