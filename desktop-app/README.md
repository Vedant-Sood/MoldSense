# MoldSense desktop app

Version **2.0.0-rc1**. The default launcher opens the Python/Tkinter research workspace with pyserial, SQLite, NumPy, SciPy and Matplotlib. The original app remains available with `--legacy`.

## Setup and launch

From this directory on Windows with Python 3.11+ and Tk:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_dashboard.py
```

`start_dashboard.ps1` prefers the local environment. Linux uses `.venv/bin/python` and may need an OS Tk package. `requirements.txt` gives dependency ranges; `requirements-validated.txt` preserves the September environment rather than a new lock file.

Use the integrated [protocol-v1 firmware](../firmware/esp32/MoldSense/). Older logger/capture firmware uses its own transfer tools or the legacy app. Close Serial Monitor before using its COM port.

Read [the research workflow](RESEARCH_README.md) for sessions, calibration, graphs, labels and exports, and [the data contract](docs/RESEARCH_DESIGN.md) for formulas/provenance.

## Local data

Records default to `%LOCALAPPDATA%\MoldSense\UserDashboard`, including `research.sqlite3`. `MOLDSENSE_DATA_DIR` overrides this root. Keep live databases, archives and exports out of Git. Close the app before copying its database or use a SQLite-aware backup including active WAL state.

Experimental reference captures stay local under the ignored `baselines/` data files. The app works without them, and tests generate synthetic references in temporary directories. Keep the assets and baselines directory beside Python source when packaging.

## Verification

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python run_dashboard.py --self-test ../outputs/desktop-self-test.json
python tests/ui_smoke.py
```

Self-test and synthetic UI smoke disable serial discovery. They need a graphical desktop or display server. The smoke writes synthetic figures/reports under ignored `outputs/`.

## Windows packages

Install `requirements-build.txt` in the environment, then run `build_research.ps1` for a portable research directory; keep `_internal` beside its executable. `build_windows.ps1` retains the one-file/installer path with corrected research version metadata. Run packaging explicitly on a Windows development machine; CI checks source/logic rather than distributing installers.

Before publishing a binary, run its offline self-test and retain dependency notices. No executable/installer is part of this source import.
