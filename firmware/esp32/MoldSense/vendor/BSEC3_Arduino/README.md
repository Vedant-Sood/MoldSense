# BSEC3 Arduino wrapper

This project-local Arduino library uses the official Bosch BSEC 3.3.0.0
headers and ESP32 binary from `bsec_v3-3-0-0.zip`. The public wrapper is
adapted from Bosch's BSEC2 Arduino wrapper for the BSEC 3 multi-instance API.

It is intentionally named `BSEC3_Arduino` and exposes `bsec3.h` / `Bsec3` so
it can coexist with an installed `bsec2` library without replacing it.
