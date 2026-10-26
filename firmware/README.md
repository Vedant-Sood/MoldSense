# Firmware

Use [esp32/MoldSense/](esp32/MoldSense/) for the integrated research instrument. Its sketch directory retains `MoldSense` to match `MoldSense.ino`.

Earlier generations live in `legacy/`; standalone test/capture programs live in `tools/`. Each preserves its sketch folder/name and Python utilities. See [compatibility](../docs/ARCHITECTURE.md) before choosing a pairing. Main firmware tests/pins do not certify historical sketches.

Start with [toolchain/SDK setup](../docs/FIRMWARE_SETUP.md), then the sketch's README, protocol, science and bench procedure. Build/test scripts do not flash devices.
