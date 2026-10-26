# Verification — repository import, 2026-10-26

The original release-candidate versions and protocol remain unchanged. Original source folders were not modified and no device was flashed.

| Check | Result |
| --- | --- |
| Original desktop suite | PASS: 23 tests before repository fixes |
| Desktop suite before data exclusion | PASS: 25 tests on Windows Python 3.13 and cloud Linux Python 3.12 |
| Public-source desktop suite | PASS: 28 tests in cloud Linux, including synthetic references, missing-reference UI behavior and parser regressions |
| Offline desktop self-test | PASS: eight Tk views, Matplotlib, scientific imports and SQLite; serial disabled |
| Full synthetic UI smoke | PASS: eight tabs, live plots, five analysis modes, presentation, pause-view, table pagination and report export |
| PowerShell syntax | PASS: application and firmware scripts parsed |
| Source archive | PASS: tracked files packaged with per-file SHA-256 and ZIP integrity verification |
| SDK bootstrap/check | PASS: pinned local 3.3.0.0 artifacts verified |
| Repository checks | PASS: tracked-source syntax, links, sketch names, excluded paths and secret patterns |
| Cloud C++ host suite | PASS: 624 assertions with Linux g++; real serializer output matches the desktop fixture byte-for-byte |
| Local ESP32 build | Blocked by the Windows cross-compiler DLL loader before compilation; this is not a successful fresh board build |
| Historical firmware build | September notes record 465556 bytes flash / 47508 bytes global RAM; retained as historical evidence only |
| Hardware/field qualification | Not rerun; no on-device, electrical or mold-model validation claimed |

The inherited host suite exercises production risk, calibration, persistence and protocol modules with mocks. The cloud rerun used Linux g++ and compared its actual serializer output with the desktop fixture. CI repeats those checks. It does not exercise the Bosch binary or ESP32 hardware. See the Actions run for the status of that check.

Current checks include focused regression cases for huge telemetry numbers and invalid protocol-version types, SDK hash checking, Python syntax, documentation links, sketch/folder matching, excluded-artifact checks and secret-pattern scanning. Pattern scans are not an exhaustive security audit.

The default screening index remains unvalidated and no trained mold model is enabled. Bench/field release gates remain in the firmware validation guide. Windows installers were not rebuilt for this source publication.

Local runtime: Python 3.13.9, NumPy 2.3.5, SciPy 1.16.3, Matplotlib 3.10.6, pyserial 3.5. The original requirements-validated.txt remains a historical environment record.

The earlier Windows host-toolchain failure was resolved for portable verification by running the production host suite in the cloud. This does not replace an ESP32 board build or bench test.

Cloud runtime: Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, Matplotlib 3.10.8 and pyserial 3.5.

Public-source publication excludes all historical sensor captures and personal filesystem paths. The legacy app handles absent local references; the test suite generates temporary synthetic signals instead of requiring experimental data. The Windows shortcut launcher resolves paths relative to its own directory.
