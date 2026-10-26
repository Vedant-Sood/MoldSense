"""Validate MoldSense HP-354 captures before BME AI-Studio import."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


EXPECTED_KEYS = [
    "sensor_index",
    "sensor_id",
    "timestamp_since_poweron",
    "real_time_clock",
    "temperature",
    "pressure",
    "relative_humidity",
    "resistance_gassensor",
    "heater_profile_step_index",
    "scanning_enabled",
    "scanning_cycle_index",
    "label_tag",
    "error_code",
]

EXPECTED_PROFILE = [
    [320, 5],
    [100, 2],
    [100, 10],
    [100, 30],
    [200, 5],
    [200, 5],
    [200, 5],
    [320, 5],
    [320, 5],
    [320, 5],
]


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"invalid JSON: {exc}"]

    for key in ("configHeader", "configBody", "rawDataHeader", "rawDataBody"):
        if key not in document:
            errors.append(f"missing top-level key: {key}")
    if errors:
        return errors

    header = document["configHeader"]
    if header.get("boardType") != "board_8":
        errors.append("configHeader.boardType must be board_8")
    if header.get("boardMode") != "heater_profile_exploration":
        errors.append("configHeader.boardMode must be heater_profile_exploration")
    if header.get("boardLayout") != "grouped":
        errors.append("configHeader.boardLayout must be grouped")

    body = document["configBody"]
    profiles = body.get("heaterProfiles", [])
    if len(profiles) != 1:
        errors.append("exactly one heater profile is required")
    elif (
        profiles[0].get("id") != "heater_354"
        or profiles[0].get("timeBase") != 140
        or profiles[0].get("temperatureTimeVectors") != EXPECTED_PROFILE
    ):
        errors.append("heater_354 profile does not match the known-good HP-354 profile")

    columns = document["rawDataBody"].get("dataColumns", [])
    column_keys = [column.get("key") for column in columns]
    column_ids = [column.get("colId") for column in columns]
    if column_keys != EXPECTED_KEYS:
        errors.append("the 13 data-column keys or their order are incorrect")
    if column_ids != list(range(1, 14)):
        errors.append("data-column IDs must be 1 through 13")

    rows = document["rawDataBody"].get("dataBlock", [])
    if not rows:
        errors.append("dataBlock contains no readings")
        return errors

    previous_timestamp = -1
    previous_cycle = -1
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, list) or len(row) != 13:
            errors.append(f"row {index}: expected 13 values")
            continue
        numeric_indices = (0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12)
        if any(
            isinstance(row[position], bool)
            or not isinstance(row[position], (int, float))
            or not math.isfinite(float(row[position]))
            for position in numeric_indices
        ):
            errors.append(f"row {index}: invalid numeric value")
            continue
        if row[0] != 0:
            errors.append(f"row {index}: sensor_index must be 0")
        if row[2] < previous_timestamp:
            errors.append(f"row {index}: timestamp moved backwards")
        previous_timestamp = row[2]
        if not (-40.0 <= row[4] <= 100.0):
            errors.append(f"row {index}: temperature is outside the plausible sensor range")
        if not (300.0 <= row[5] <= 1100.0):
            errors.append(f"row {index}: pressure must be in hPa")
        if not (0.0 <= row[6] <= 100.0):
            errors.append(f"row {index}: relative humidity is outside 0-100 percent")
        if row[7] <= 0:
            errors.append(f"row {index}: gas resistance must be positive")
        if row[8] not in range(10):
            errors.append(f"row {index}: heater step must be 0-9")
        if row[9] is not True:
            errors.append(f"row {index}: scanning_enabled must be true")
        if row[10] < previous_cycle:
            errors.append(f"row {index}: scanning cycle moved backwards")
        previous_cycle = row[10]
        if row[12] != 0:
            errors.append(f"row {index}: BME error_code is {row[12]}")

    # Every complete ten-row scan must preserve the HP-354 step order. A final
    # partial scan is valid when power is removed during acquisition.
    for cycle in sorted({int(row[10]) for row in rows if len(row) == 13}):
        steps = [int(row[8]) for row in rows if len(row) == 13 and int(row[10]) == cycle]
        if len(steps) == 10 and steps != list(range(10)):
            errors.append(f"cycle {cycle}: heater steps are not ordered 0 through 9")
        elif len(steps) > 10:
            errors.append(f"cycle {cycle}: contains more than 10 heater steps")

    if errors:
        return errors

    complete_cycles = sum(
        1
        for cycle in {int(row[10]) for row in rows}
        if len([row for row in rows if int(row[10]) == cycle]) == 10
    )
    print(
        f"VALID {path}: rows={len(rows)}, complete_cycles={complete_cycles}, "
        f"boardType={header['boardType']}, profile=heater_354"
    )
    return []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    failed = False
    for path in args.files:
        errors = validate(path)
        if errors:
            failed = True
            print(f"INVALID {path}")
            for error in errors:
                print(f"  - {error}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
