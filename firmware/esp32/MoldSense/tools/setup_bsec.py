"""Install only the pinned Bosch SDK artifacts from a locally licensed package."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "bsec-sdk.json"
SKIP = {".git", ".venv", "__pycache__", "build", "dist", "release", "release_research", "old_data"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def profile_bytes(data):
    """Read a binary config or a decimal/hex C initializer without executing it."""
    expected = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"][-1]
    if digest(data) == expected["profile_sha256"]:
        return data
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError:
        return None
    text = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
    arrays = re.findall(r"\{([^{}]+)\}", text)
    if not arrays:
        arrays = [text]
    for array in arrays:
        tokens = [t.strip() for t in array.split(",") if t.strip()]
        if not tokens or any(not re.fullmatch(r"(?:0[xX][0-9a-fA-F]+|\d+)", t) for t in tokens):
            continue
        try:
            values = bytes(int(t, 16) if t.lower().startswith("0x") else int(t) for t in tokens)
        except ValueError:
            continue
        if digest(values) == expected["profile_sha256"]:
            return values
    return None


def matches(data, entry):
    if "profile_sha256" in entry:
        return profile_bytes(data) is not None
    return len(data) == entry["bytes"] and digest(data) == entry["sha256"]


def check(entries):
    missing = []
    for entry in entries:
        target = ROOT / entry["path"]
        if not target.is_file() or not matches(target.read_bytes(), entry):
            missing.append(entry["path"])
    if missing:
        raise SystemExit("Missing or mismatched BSEC 3.3.0.0 artifacts:\n" + "\n".join(missing)
                         + "\nRun setup_bsec.py --source PATH using the matching licensed SDK/profile.")
    print("PASS: BSEC 3.3.0.0 headers, ESP32 algorithm and default IAQ profile verified")


def install(source, entries, replace=False):
    source = source.resolve()
    if not source.is_dir():
        raise SystemExit("SDK source must be an existing extracted directory")
    selected = {}
    names = {Path(e["path"]).name for e in entries}
    for parent, dirs, files in os.walk(source):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for name in sorted(files):
            path = Path(parent) / name
            if name not in names and path.suffix.lower() not in {".c", ".h", ".txt", ".config"}:
                continue
            if path.stat().st_size > 1_000_000:
                continue
            data = path.read_bytes()
            for entry in entries:
                key = entry["path"]
                if key in selected:
                    continue
                if "profile_sha256" not in entry and name != Path(key).name:
                    continue
                if matches(data, entry):
                    if "profile_sha256" in entry and digest(data) != entry["sha256"]:
                        values = profile_bytes(data)
                        data = ("#pragma once\n#include <stdint.h>\n"
                                "// Locally installed Bosch BSEC 3.3.0.0 IAQ profile.\n"
                                "static const uint8_t defaultIaqConfig[] = {"
                                + ",".join(map(str, values)) + "};\n").encode("utf-8")
                    selected[key] = data
        if len(selected) == len(entries):
            break
    missing = [e["path"] for e in entries if e["path"] not in selected]
    if missing:
        raise SystemExit("No complete matching SDK/profile found; nothing installed:\n" + "\n".join(missing))
    # Validate every input and conflict before making any destination changes.
    for name, data in selected.items():
        target = ROOT / name
        if target.exists() and target.read_bytes() != data and not replace:
            raise SystemExit("Existing artifact differs; review it before using --replace: " + name)
    for name, data in selected.items():
        target = ROOT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    check(entries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--source", type=Path, help="Extracted licensed SDK, library or original firmware directory")
    mode.add_argument("--check", action="store_true", help="Verify local artifacts without changing them")
    parser.add_argument("--replace", action="store_true", help="Replace a reviewed existing local artifact")
    args = parser.parse_args()
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    if args.check:
        check(entries)
    else:
        install(args.source, entries, args.replace)


if __name__ == "__main__":
    main()
