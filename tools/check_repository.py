"""Check tracked source paths, Python syntax, document links and accidental secrets."""
from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RESTRICTED = {
    "firmware/esp32/MoldSense/vendor/BSEC3_Arduino/src/inc/bsec_datatypes.h",
    "firmware/esp32/MoldSense/vendor/BSEC3_Arduino/src/inc/bsec_interface.h",
    "firmware/esp32/MoldSense/src/Models/DefaultIaqConfig.h",
    "firmware/esp32/MoldSense/src/Models/MoldModelData.h",
}
BAD_PARTS = {".local", ".venv", "__pycache__", "old_data", "build", "dist", "release_research"}
BAD_SUFFIXES = {".exe", ".dll", ".a", ".bin", ".db", ".sqlite3", ".pem", ".key", ".bmerawdata"}
TEXT_SUFFIXES = {".py", ".cpp", ".h", ".ino", ".md", ".json", ".yml", ".ps1", ".txt", ".cmd", ".vbs"}
SECRET = re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|"
                    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")


def tracked_files():
    result = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"],
                            check=True, capture_output=True)
    names = [p.decode("utf-8") for p in result.stdout.split(b"\0") if p]
    if not names:
        raise RuntimeError("No tracked files: stage the intended source files first.")
    return names


def validate(names):
    errors = []
    for name in names:
        relative = PurePosixPath(name)
        path = ROOT / name
        if (name in RESTRICTED or set(relative.parts) & BAD_PARTS
                or path.suffix.lower() in BAD_SUFFIXES or relative.name.startswith(".env")):
            errors.append("Excluded local/generated/restricted artifact: " + name)
        if not path.resolve().is_relative_to(ROOT) or path.is_symlink():
            errors.append("Unexpected file target: " + name)
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeError:
            errors.append("Non-UTF-8 source: " + name)
            continue
        if SECRET.search(text):
            errors.append("Possible credential/private key in " + name)
        if path.suffix == ".py":
            try:
                ast.parse(text, filename=name)
            except SyntaxError as exc:
                errors.append(f"Python syntax error: {name}:{exc.lineno}")
        if path.suffix == ".md":
            # Historical snapshots/upstream documentation retain original paths.
            if ("docs/history/" in name or "/vendor/" in name
                    or "/legacy/" in name or "firmware/tools/" in name):
                continue
            for link in re.findall(r"\[[^\]]*\]\(([^)\n]+)\)", text):
                link = link.strip("<>").split("#", 1)[0]
                if not link or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", link):
                    continue
                if not (path.parent / link).exists():
                    errors.append(f"Broken local link in {name}: {link}")
    for path in (ROOT / "firmware").rglob("*.ino"):
        if ".local" not in path.parts and path.stem != path.parent.name:
            errors.append("Arduino sketch/folder mismatch: " + path.relative_to(ROOT).as_posix())
    return errors


def main():
    names = tracked_files()
    errors = validate(names)
    if errors:
        print("\n".join(errors))
        return 1
    print(f"PASS: {len(names)} tracked files; source syntax, paths, links and secret-pattern checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
