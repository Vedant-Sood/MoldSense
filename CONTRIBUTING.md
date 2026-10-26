# Contributing

Use `desktop-app/` for Python and `firmware/esp32/MoldSense/` for supported ESP32 firmware. Earlier sketches belong under `firmware/legacy/`; keep each `.ino` inside a matching sketch folder. Keep dependencies, binaries and personal data out of commits.

## Development checks

1. Install `desktop-app/requirements.txt` in a virtual environment.
2. Run `python -m unittest discover -s desktop-app/tests -p "test_*.py" -v`.
3. For C++ changes, run `python firmware/esp32/MoldSense/tools/run_tests.py --compiler g++` and build the ESP32 target with the pinned SDK/core.
4. Run `python tools/check_repository.py` and `git diff --check`.
5. For UI changes, run `python desktop-app/run_dashboard.py --self-test outputs/self-test.json`. For full synthetic coverage, run `python desktop-app/tests/ui_smoke.py`. Both disable serial discovery.

Add focused regression tests for changed behavior. Host mocks verify application logic; they cannot establish electrical correctness, on-device timing or scientific validity.

## Commits and pull requests

Keep commits focused and use an imperative subject, such as `fix(desktop): reject oversized numeric telemetry` or `docs: explain ESP32 setup`. Separate source imports, behavior fixes and documentation where practical. Preserve shared branch history.

Describe the trigger, resulting behavior, checks actually run and material limitations. Update both sides of a serial-contract change, its documentation and the cross-language fixture. Do not claim compatibility with an unchecked firmware generation.

## Data and experiments

Preserve original measurements and packets. Mark synthetic fixtures clearly. Ground-truth labels must be independent of the instrument's score. Do not publish flash backups, calibration state, personal databases, credentials or identifiable location notes. Keep experimental reference captures local, preserve their provenance, and do not present them as mold-validation data.

## Dependencies

Retain upstream notices. Install restricted Bosch SDK artifacts locally with `setup_bsec.py`; their paths are ignored. Review dependency/profile updates together with hashes, wrapper compatibility and board compilation. Publishing a Windows binary or flashing hardware is a separate release operation.
