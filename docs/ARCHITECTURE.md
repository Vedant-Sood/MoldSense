# Architecture and compatibility

The instrument acquires wall-probe and BME688 observations, maintains independent wall/BSEC state, and publishes protocol-v1 NDJSON over USB serial at 115200 baud. The desktop validates identity and framing, stores originals in SQLite, and calculates separately named derived statistics for plots and exports.

| Layer | Main files | Responsibility |
| --- | --- | --- |
| ESP32 entry/configuration | `firmware/esp32/MoldSense/MoldSense.ino`, `Config.h`, `src/App.cpp` | Pins, scheduling, switches and guarded commands |
| Sensors/calibration | `src/Sensors/`, `src/Calibration/` | Freshness/validity, filtering and dry-reference calibration |
| Analysis/storage/UI | `src/Analysis/`, `src/Storage/`, `src/UI/` | Screening index, independent persisted state, OLED and serial |
| Desktop transport | `research/protocol.py`, `research/acquisition.py` | Bounded framing, identity, reconnect and checked downloads |
| Desktop records/analysis | `research/database.py`, `statistics.py`, `migration.py` | Original packets, sessions, labels and statistical policy |
| Desktop presentation | `research/ui*.py`, `plots.py`, `exports.py` | Eight views, charts, figures and reports |

Firmware module paths are relative to the main sketch; desktop modules are under `desktop-app/moldsense_user/`.

## Firmware generations

| Location | Role | Desktop pairing |
| --- | --- | --- |
| `firmware/esp32/MoldSense/` | Integrated firmware 1.0.0-rc1 | Default research app, protocol 1 |
| `firmware/legacy/moldsense_firmware/` | Earlier BSEC/capture firmware with DHT22 verifier | Legacy archives; not protocol-v1 acquisition |
| `firmware/legacy/moldsensecodev2.0/` | Earlier switch-controlled BSEC/capture variant | Legacy archive workflow |
| `firmware/legacy/bme688_logger/` | Earlier logger | Its own transfer tools / legacy workflow |
| `firmware/tools/one_shot_bme_ai_capture/` | Full heater-profile capture | AI-Studio tooling |
| `firmware/tools/esp32_comb_capacitance/` | Standalone probe test | Serial diagnostics |

Historical sketches retain their original dependency requirements and were not certified by the integrated firmware's tests.

Wall calibration does not reset BSEC learning. Gas resistance is not itself mold classification. IAQ and AI-scan profiles have different heater schedules. A future validated mold model must be imported deliberately; historical model exports are not activated by this import.
