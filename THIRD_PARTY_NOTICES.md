# Third-party notices

The root MIT license applies to project-authored code. It does not relicense upstream dependencies or Bosch SDK artifacts.

| Component | Snapshot version | Terms / location |
| --- | --- | --- |
| Modified Bosch BSEC Arduino wrapper | 3.3.0 wrapper | BSD-3-Clause notices in `firmware/esp32/MoldSense/vendor/BSEC3_Arduino/src/bsec3.*` |
| Bosch BME68x Sensor library | 1.3.40408 | BSD licenses in its vendor directory and `src/bme68x/` |
| Adafruit SSD1306 | 2.5.17 | Vendor `license.txt` |
| Adafruit GFX | 1.12.6 | Vendor `license.txt` |
| Adafruit BusIO | 1.17.4 | Vendor `LICENSE` |
| Bosch algorithm, interface headers and default profile | 3.3.0.0 | Separately obtained SDK; excluded from Git; Bosch terms apply |
| Espressif Arduino ESP32 core | 3.3.10 | External toolchain, not vendored |
| Python runtime packages | See desktop requirements | Installed externally; upstream licenses apply |

The BSEC wrapper adaptation changes pressure input to Pa, fixes uptime wrapping and avoids copying callback state. The algorithm is unmodified. The setup tool installs hash-matching artifacts; it does not accept a license on the user's behalf or download a package.

Obtain SDK software and its license from the [Bosch software page](https://www.bosch-sensortec.com/en/software-tools/software/bme688-and-bme690-software). This project is not endorsed or certified by Bosch, Espressif or Adafruit.
