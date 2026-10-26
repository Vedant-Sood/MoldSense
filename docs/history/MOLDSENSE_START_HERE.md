# MoldSense integrated release candidate

Firmware 1.0.0-rc1 + Windows research application 2.0.0-rc1. Read [work completed and remaining qualification](MOLDSENSE_WORK_LIST.md) first.

- [Firmware, GPIO wiring and calibration](MoldSense/README.md)
- [Desktop run guide and experiment workflow](moldsenseusercodev1/RESEARCH_README.md)
- [USB protocol](MoldSense/docs/PROTOCOL.md)
- [Scientific model and limitations](MoldSense/docs/SCIENCE.md)
- [Database and analysis contract](moldsenseusercodev1/docs/RESEARCH_DESIGN.md)
- [Software tests and hardware qualification](MoldSense/docs/VALIDATION.md)

For the packaged Windows application, extract the entire ZIP first and run `Windows/MoldSense-Research-2.0.0-rc1/MoldSense-Research-2.0.0-rc1.exe`. Keep `_internal` beside the executable. No Python installation is needed for this portable build. The source launcher is in `moldsenseusercodev1`; its separate older application is available with --legacy. Existing installed 1.1 executables are unchanged.

Compiled ESP32 binaries are in `MoldSense/build`. They target **classic ESP32 DOIT DevKit V1**, not ESP32-S3. No upload was performed. Back up and verify existing flash/files before an explicitly authorized upload. Review the GPIO section for the confirmed bare copper-comb touch plate.

The archive includes a per-file SHA-256 manifest and test evidence. Its accompanying SHA256SUMS.txt and RELEASE_VERIFICATION.json verify packaging. Synthetic QA figures are clearly labelled and are not experimental results. No trained mold model is supplied; the 0–100 index is an unvalidated screening score.
