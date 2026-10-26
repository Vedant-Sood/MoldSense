# MoldSense BME688 logger

This ESP32 sketch keeps a BSEC baseline in LittleFS across ordinary power loss, writes session data to permanent CSV, and exposes a serial file store. It supports two independent BSEC states:

- Normal IAQ baseline: `/bsec_state.bin`
- AI-model baseline: `/bsec_model_state.bin`

The normal state is created when BSEC reaches confidence 3 and is refreshed at confidence 2 or higher. Do not erase LittleFS or issue `CLEAR_STATE` unless you deliberately want to start that baseline over.

## Important AI-Studio boundary

`/bme688_sessions_v2.csv` is a durable observation log, useful for review and external analysis. It is **not** a BME AI-Studio training import by itself: AI-Studio training requires the raw scan format with a defined multi-step heater profile, gas-index data, and matching metadata. The existing logger runs BSEC low-power IAQ mode and records one processed sample per minute.

Once you train a model in BME AI-Studio using compatible raw scan data, export the BSEC configuration for the same BSEC version shown at ESP32 boot. The generated C array can be converted to raw bytes and uploaded as `/bsec_model.bin`; `MODEL_ENABLE` selects it for the next reboot. On the next boot, the sketch uses BSEC scan mode and logs class 1–4 probabilities in the v2 CSV. Keep the mapping from class number to your label (for example, `clean`, `mold`) with the AI-Studio project on your PC.

The BME688 does not identify biological mold on its own. A classifier needs properly labelled clean and mold-affected examples, matching controls, and validation data. Treat it as a gas-pattern indicator, not proof of mold or a health/safety clearance.

## Install and run

1. Install the Espressif ESP32 board package, `Bosch_BSEC2_Library`, and `Bosch_BME68x_Library`.
2. Put Wi-Fi credentials into the sketch if you want wall-clock timestamps; otherwise records remain traceable by `boot_id` and `uptime_ms`.
3. Flash `bme688_logger.ino`.
4. Use `DUMP` or run `python download_bme688_log.py` over USB to retrieve the CSV.

## Serial commands

- `STATE_INFO`, `SAVE_STATE`, `DUMP_STATE`, `IMPORT_STATE <hex>`, `CLEAR_STATE`: inspect or manage the currently active BSEC state.
- `DUMP`, `SIZE`, `CLEAR_LOG`: manage the v2 observation CSV.
- `FILES`: list permanent LittleFS files and their byte sizes.
- `FILE_DUMP /name`: print any file as hex between markers.
- `FILE_DELETE /name`: permanently delete a user file. BSEC state files are protected.
- `FILE_UPLOAD_BEGIN /name bytes`: start an atomic upload.
- `FILE_UPLOAD_HEX hexbytes`: send one chunk (2–512 hex characters).
- `FILE_UPLOAD_END` or `FILE_UPLOAD_ABORT`: finish or discard the upload.
- `MODEL_INFO`: report whether a model is selected/active and its stored size.
- `MODEL_ENABLE` / `MODEL_DISABLE`: select or deselect `/bsec_model.bin` for the next reboot. The model file is kept when disabled.

For files larger than a short manual paste, use `transfer_bme688_file.py`:

```text
python transfer_bme688_file.py upload model.bin /bsec_model.bin --port COM3
python transfer_bme688_file.py download /bsec_model.bin copied_model.bin --port COM3
python transfer_bme688_file.py c-array-to-bin exported_model.c model.bin
```

After the upload, send `MODEL_ENABLE`, then restart power. If boot prints `AI-STUDIO MODEL ACTIVE`, it was accepted by BSEC. If it prints a model error, keep the model disabled and check that the exported configuration targets the same BSEC major/minor version as the installed Arduino library.
