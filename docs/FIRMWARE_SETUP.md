# Firmware setup

Use a classic ESP32 DOIT DevKit V1. Read the [pin map](../firmware/esp32/MoldSense/README.md) before attaching hardware.

## Toolchain

Install [Arduino CLI](https://docs.arduino.cc/arduino-cli/installation/) and Espressif's core on a connected machine:

```powershell
arduino-cli core update-index --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core install esp32:esp32@3.3.10 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
```

The Adafruit/BME68x libraries and adapted BSEC wrapper are pinned in `firmware/esp32/MoldSense/vendor/`. Use this wrapper for the integrated firmware; another similarly named installation is not equivalent.

## Local Bosch SDK

Obtain BSEC **3.3.0.0** and its terms from [Bosch](https://www.bosch-sensortec.com/en/software-tools/software/bme688-and-bme690-software); earlier releases may be under the archive link. Extract it locally. Required: **classic ESP32**, selectivity-capable headers, and the **BME688 3.3 V / 3 s / four-day IAQ profile**. No newer SDK, IAQ-only header or ESP32-S3 binary is silently substituted.

From the repository root:

```powershell
python firmware/esp32/MoldSense/tools/setup_bsec.py --source "C:\path\to\extracted-sdk"
python firmware/esp32/MoldSense/tools/setup_bsec.py --check
```

The installer locates matching `bsec_datatypes.h`, `bsec_interface.h`, `libalgobsec.a` and IAQ profile using `bsec-sdk.json`. It accepts an original complete MoldSense firmware folder, complete BSEC Arduino library, or extracted SDK containing those artifacts. Arrays in `.h`, `.c`, `.txt` and binary `.config` profiles are supported. If the archive omits that IAQ profile, supply its matching profile export or the original complete firmware folder. Missing/mismatched input aborts before installation. No network or serial access occurs.

Installed SDK headers, algorithm and generated `DefaultIaqConfig.h` are ignored by Git. Preserve their local copy with the original terms. Do not add them to a commit or source archive.

## Compile

```powershell
powershell -NoProfile -File firmware/esp32/MoldSense/tools/build.ps1
```

Add `-ArduinoCli "C:\path\to\arduino-cli.exe"` when it is outside PATH, or `-ConfigFile "C:\path\to\arduino-cli.yaml"` for a separate CLI configuration. The script checks the SDK first and writes to ignored `build/`; it does not connect, upload, erase or format.

Arduino IDE: install completed vendor libraries into the sketchbook library directory, open `firmware/esp32/MoldSense/MoldSense.ino`, and select DOIT ESP32 DEVKIT V1 with core 3.3.10.

Host tests need Python and a C++17 compiler, without the SDK:

```powershell
python firmware/esp32/MoldSense/tools/run_tests.py --compiler g++
```

PlatformIO uses a different core and requires separate verification. Use Arduino as the reference build path. For device upload, verify board/port/partitions and retain flash/data backups; follow the [bench procedure](../firmware/esp32/MoldSense/docs/VALIDATION.md).
