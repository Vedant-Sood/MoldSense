"""Create a verified source-only archive from the Git-tracked working tree."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

from check_repository import ROOT, tracked_files, validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/releases/MoldSense-source.zip")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT):
        raise SystemExit("Choose an output under the repository's outputs directory.")
    if output.exists():
        raise SystemExit("Output already exists; choose a new archive path.")
    names = tracked_files()
    errors = validate(names)
    if errors:
        raise SystemExit("\n".join(errors))
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "kind": "source-only working tree",
        "excluded": ["local Bosch SDK", "toolchains", "executables", "personal databases", "device backups"],
        "files": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(names):
            data = (ROOT / name).read_bytes()
            manifest["files"].append({"path": name, "bytes": len(data),
                                      "sha256": hashlib.sha256(data).hexdigest()})
            archive.writestr("MoldSense/" + name, data)
        archive.writestr("MoldSense/FILE_MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("ZIP integrity check failed")
        for item in manifest["files"]:
            if hashlib.sha256(archive.read("MoldSense/" + item["path"])).hexdigest() != item["sha256"]:
                raise RuntimeError("Archive checksum mismatch: " + item["path"])
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(checksum + "  " + output.name + "\n", encoding="ascii")
    print(f"PASS: {len(names)} files verified in {output}")


if __name__ == "__main__":
    main()
