# MoldSense three-mode firmware

This is the main firmware for one BME688 connected by I2C to a DOIT ESP32 DevKit V1. It preserves the earlier logger and adds three deliberately separated operating modes:

| Mode | Purpose | Stored output |
|---|---|---|
| `LOG` | Continuous IAQ/environment logging with a persistent BSEC 3 baseline | `/environment.csv`, `/bsec3_state.bin` |
| `CAPTURE` | Bosch HP-354 ten-step raw scans for AI-Studio training | `/cap_N.bmerawdata` |
| `TEST` | Two-to-four-class inference from an uploaded AI-Studio/BSEC model | `/environment.csv`, `/bsec3_model_state.bin` |

The selected mode is stored in ESP32 NVS and survives restarts. A mode change safely ends the current session, saves BSEC state where applicable, and restarts the ESP32 so only one sensor engine owns the BME688 at a time.

## Required libraries

- Espressif ESP32 board package
- Bosch `BME68x Sensor library`
- Project `BSEC3_Arduino` library (installed beside, not over, Bosch `bsec2`)
- Adafruit `Adafruit SSD1306`, `Adafruit GFX Library`, and `Adafruit BusIO`
- Python `pyserial` for the optional PC utility

Open `moldsense_firmware.ino` in Arduino IDE, select **DOIT ESP32 DEVKIT V1**, and upload it. The sketch uses I2C address `0x76`; change `BME_ADDRESS` in `MoldSenseConfig.h` to `0x77` if your board is wired for the high address.

## DHT22 verification sensor

The DHT22 independently checks the BME688 temperature and relative-humidity
readings every three seconds. Wire it as follows:

| DHT22 pin | ESP32 DevKit V1 |
|---|---|
| `VCC` | `3V3` |
| `DATA` | `D4` / GPIO `4` |
| `GND` | `GND` |

For a bare four-pin DHT22, leave pin 3 disconnected and add a 4.7k-10k pull-up
resistor between `DATA` and `3V3`. Three-pin modules normally include this
resistor. Keep the DHT22 beside the BME688 but away from the ESP32 regulator so
both sensors sample similar air without extra board heat.

Serial output prints both readings, signed DHT22-minus-BME688 deltas, and
`PASS`/`WARN` checks. The default limits are 2.0 C and 10 percentage points RH;
they can be changed in `MoldSenseConfig.h`. A missing or failed DHT22 prints a
read error but never stops BME688 logging, capture, or classification.

```text
VERIFY | BME688 temp=26.10C rh=57.20% | DHT22 temp=25.80C rh=58.00% | delta_temp=-0.30C delta_rh=0.80% | temp_check=PASS rh_check=PASS
```

## OLED wiring

The firmware supports a common 0.8-inch SSD1306 128x64 I2C OLED. It shares the BME688 bus:

| OLED pin | ESP32 DevKit V1 |
|---|---|
| `VCC` | `3V3` |
| `GND` | `GND` |
| `SDA` | GPIO `21` |
| `SCL` | GPIO `22` |

The display automatically tries addresses `0x3C` then `0x3D`. It shows mode, temperature, humidity, gas/IAQ values, capture progress, or TEST-class probabilities. A missing display never prevents the logger from starting.

## Clock behavior

The firmware does not use Wi-Fi. Set UTC time from Serial Monitor:

```text
CLOCK_SET 1787823135
```

Or synchronize it from the PC automatically:

```text
python moldsense_cli.py --port COM3 clock-sync
```

The ESP32 clock runs independently of Wi-Fi while powered and its latest checkpoint is saved in NVS. After a complete power unplug, the ESP32 has no battery-backed oscillator, so the restored time is marked `RESTORED_ESTIMATE` and cannot include the period it was unpowered. For accurate wall-clock time across unplugging, add a DS3231 RTC with a coin cell. Sensor data still remains safe without one because session IDs, boot IDs, and uptime are also recorded.

`/sessions.csv` journals start/end events, labels, file paths, row counts, timestamps, and clock quality. If power disappears without a clean stop, the next boot closes the old journal entry as `POWER_LOSS_OR_RESET` using its last checkpoint.

## Collect AI-Studio training data

Switch modes:

```text
MODE CAPTURE
```

After restart, collect one clearly labelled environment per capture file:

```text
CAPTURE_START mold_sample_01
CAPTURE_STOP
CAPTURE_START clean_air_01
CAPTURE_STOP
CAPTURE_START mold_sample_02
CAPTURE_STOP
```

While active, the firmware uses Bosch HP-354 in parallel mode and records every valid heater step. `CAPTURE_STOP` converts the durable row spool into the documented `.bmerawdata` JSON structure. If power fails mid-capture, the row spool remains in LittleFS and is finalized automatically the next time `CAPTURE` mode boots.

List and download captures:

```text
FILES
python moldsense_cli.py --port COM3 download /cap_1.bmerawdata mold_sample_01.bmerawdata
```

Import each `.bmerawdata` file into the BME AI-Studio specimen collection, create the appropriate specimen/class label there, and train a classification model with two to four classes. The text supplied to `CAPTURE_START` is stored in `/sessions.csv`; AI-Studio class assignment is still performed in AI-Studio.

Use multiple independent samples and sessions for every class. For mold work, include matched clean controls under similar temperature and humidity. The BME688 classifies gas-response patterns; it does not directly identify mold species or prove that an environment is safe.

## Deploy and test a classification model

In AI-Studio, export the trained classifier as a C configuration for the same BSEC version printed by this firmware at boot. Upload it with:

```text
python moldsense_cli.py --port COM3 model-upload exported_model.c
python moldsense_cli.py --port COM3 mode TEST
```

After restart, successful initialization prints:

```text
FOUR-CLASS MODEL LOADED.
```

`TEST` output reports `C1` through `C4` as percentages and appends their probabilities to `/environment.csv`. Class order is the order exported by AI-Studio, so keep that mapping with your project. Test-mode BSEC 3 learning state is stored separately in `/bsec3_model_state.bin` and is never mixed with normal IAQ state. Older BSEC 2 state remains at `/bsec_state.bin` for rollback and is never loaded by this firmware.

## Serial commands

```text
MODE
MODE LOG
MODE CAPTURE
MODE TEST
STATUS
CLOCK_SET <unix_epoch_utc>
CLOCK_INFO
CAPTURE_START <label>
CAPTURE_STOP
CAPTURE_STATUS
SAVE_STATE
BSEC_STATUS
DHT_STATUS
MODEL_INFO
FILES
FILE_READ /path
FILE_DUMP /path
FILE_DELETE /user_name
FILE_UPLOAD_BEGIN /name bytes
FILE_UPLOAD_HEX <hex>
FILE_UPLOAD_END
FILE_UPLOAD_ABORT
RESTART
HELP
```

For safety, serial writes and deletions are restricted to `/bsec_model.bin` and filenames beginning `/user_`. Capture, journal, log, and BSEC-state files can be read or downloaded but cannot be overwritten through the generic file commands.

## Storage rules

- LittleFS is never auto-formatted. A mount failure stops the firmware instead of erasing training data, states, captures, or models.
- BSEC state uses a temporary file and final rename.
- File uploads use a temporary file and are activated only after the declared byte count arrives.
- Capture files are additive; starting a new capture increments its ID instead of replacing older data.
