"""Compatibility entry point for the repository's source-only packager."""
from pathlib import Path
import runpy
import sys

tools = Path(__file__).resolve().parents[4] / "tools"
sys.path.insert(0, str(tools))
runpy.run_path(str(tools / "package_source.py"), run_name="__main__")
