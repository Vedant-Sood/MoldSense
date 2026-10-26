# One-shot BME688 AI baseline capture

This is a small, non-flashed ESP32 DevKit V1 sketch for collecting BME688
HP-354 raw readings for BME AI-Studio. It deliberately has **no DHT22 code**,
classifier, Wi-Fi, or ordinary IAQ logger. An optional SSD1306 OLED shows the
armed, reading, ended, idle, and error states plus current BME values.

## Wiring

| BME688 | ESP32 DevKit V1 |
|---|---|
| VCC | 3V3 |
| GND | GND |
| SDA | GPIO21 |
| SCL | GPIO22 |

Connect an SSD1306 128x64 I2C OLED to the same SDA/SCL pins, with VCC at 3V3
and GND at GND. Addresses `0x3C` and `0x3D` are detected automatically. A
missing OLED does not prevent BME688 capture.

The sketch automatically probes both valid BME688 addresses, `0x76` and
`0x77`.

## One-shot workflow

1. Boot the ESP32 and open Serial Monitor at 115200 baud.
2. Type `ARM_INITIALIZE clean_air_01` (replace the label as needed).
3. Wait for `ARMED_FOR_NEXT_BOOT`, then switch the ESP32 off.
4. Put the BME688 in the sample environment and switch the ESP32 on. It
   automatically starts the HP-354 capture, prints `READINGS_STARTED`, streams
   BME values in Serial Monitor, and shows them on the OLED.
5. After the desired capture period, switch the ESP32 off.
6. Switch it on once more. The sketch finalizes the power-interrupted rows as
   `/cap_N.bmerawdata`, prints and displays `READINGS_ENDED`, and remains idle.
   It will not start another capture until explicitly armed again.
7. Type `FILES`, then `FILE_READ /cap_N.bmerawdata` to retrieve the result.

`STOP_FINALIZE` is available if you want to close the capture cleanly without a
power cycle. `RESTART` performs a software reboot and is useful for a monitored
test immediately after arming.

LittleFS is never automatically formatted. If a truly blank ESP32 reports
`STORAGE_NOT_MOUNTED`, type `FORMAT_STORAGE CONFIRM` once, restart, and then arm
the capture. Do not use the format command on a board containing files you need.

The generated file uses the same 10-step HP-354 heater profile and 13-column
raw-data layout as the earlier MoldSense captures, with `boardType=board_8` for
BME AI-Studio. This records training/baseline samples; it does not load the old
BSEC2 `/bsec_state.bin` or run the trained TEST classifier.

Validate downloaded captures before importing them:

```text
python validate_bmerawdata.py cap_1.bmerawdata
```
