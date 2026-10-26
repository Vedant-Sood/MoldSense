#!/usr/bin/env python3
"""Create AI-Studio Board 688-compatible copies without altering source data."""

import json
from pathlib import Path


FILES = (
    (Path("cap_1_matched_to_cap_2.bmerawdata"), Path("cap1_fix.bmerawdata")),
    (Path("cap_2.bmerawdata"), Path("cap2_fix.bmerawdata")),
    (Path("cap_3.bmerawdata"), Path("cap3_fix.bmerawdata")),
)


for source, destination in FILES:
    document = json.loads(source.read_text(encoding="utf-8"))
    document["configHeader"]["boardType"] = "board_8"
    destination.write_text(
        json.dumps(document, separators=(",", ":")),
        encoding="utf-8",
    )
    rows = len(document["rawDataBody"]["dataBlock"])
    print(f"Created {destination}: boardType=board_8, rows={rows}")
