# MoldSense documentation

[Project overview and quick start](../README.md)

MoldSense combines the desktop research application and the integrated ESP32
instrument. Use matching protocol-v1 components for live acquisition.

| Task | Guide |
| --- | --- |
| Run the desktop app and review saved sessions | [Desktop guide](../desktop-app/README.md) |
| Follow the research workflow | [Research README](../desktop-app/RESEARCH_README.md) |
| Set up the board and proprietary Bosch SDK locally | [Firmware setup](FIRMWARE_SETUP.md) |
| Check pin assignments, switches and firmware commands | [Integrated firmware guide](../firmware/esp32/MoldSense/README.md) |
| Understand the desktop/firmware boundary | [Architecture](ARCHITECTURE.md) |
| Integrate another serial client | [Protocol](../firmware/esp32/MoldSense/docs/PROTOCOL.md) |
| Understand data storage and analysis | [Research design](../desktop-app/docs/RESEARCH_DESIGN.md) |
| Review screening assumptions | [Science](../firmware/esp32/MoldSense/docs/SCIENCE.md) |
| Check recorded software verification | [Repository verification](VERIFICATION.md) |
| Plan bench and field qualification | [Firmware validation](../firmware/esp32/MoldSense/docs/VALIDATION.md), [desktop validation](../desktop-app/docs/RESEARCH_VALIDATION.md) |
| Find standalone capture tools and earlier sketches | [Tools](../firmware/tools/README.md), [legacy firmware](../firmware/legacy/README.md) |
| Understand the source import | [Source provenance](SOURCE_PROVENANCE.md) |
| Contribute or redistribute | [Contributing](../CONTRIBUTING.md), [third-party notices](../THIRD_PARTY_NOTICES.md) |

## Current scope

The desktop can inspect saved sessions without connected hardware. Live work
requires the integrated firmware and exclusive access to the serial port.

The default 0–100 screening index is unvalidated and is not a calibrated
probability of mold. No validated mold classifier is included. Host-side
software checks do not replace an ESP32 build, electrical tests or field
qualification. Bosch SDK components retain their separate terms.

The [verification report](VERIFICATION.md) records prior checks and their limits;
this documentation index does not report a new hardware or software test run.
