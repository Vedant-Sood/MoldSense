#!/usr/bin/env python3
"""Create a row-matched BME AI-Studio file and compare two capture profiles."""

import json
import statistics
from pathlib import Path


DATASET_1 = Path("cap_1.bmerawdata")
DATASET_2 = Path("cap_2.bmerawdata")
MATCHED = Path("cap_1_matched_to_cap_2.bmerawdata")
REPORT = Path("cap_1_vs_cap_2_deviation.md")

COL = {
    "temperature": 4,
    "pressure": 5,
    "humidity": 6,
    "gas": 7,
    "heater_step": 8,
}


def median(rows, column):
    return statistics.median(float(row[column]) for row in rows)


def symmetric_deviation(a, b):
    denominator = abs(a) + abs(b)
    return 0.0 if denominator == 0 else 200.0 * abs(a - b) / denominator


def main():
    first = json.loads(DATASET_1.read_text(encoding="utf-8"))
    second = json.loads(DATASET_2.read_text(encoding="utf-8"))
    rows_1 = first["rawDataBody"]["dataBlock"]
    rows_2 = second["rawDataBody"]["dataBlock"]

    if len(rows_1) < len(rows_2):
        raise ValueError("Dataset 1 has fewer rows than dataset 2")

    # A contiguous prefix preserves the heater sequence and compares the same
    # stage of each session instead of cherry-picking scattered measurements.
    matched_rows = rows_1[: len(rows_2)]
    matched_data = dict(first)
    matched_data["rawDataHeader"] = dict(first["rawDataHeader"])
    matched_data["rawDataHeader"]["seedPowerOnOff"] = "capture_1_matched_to_capture_2"
    matched_data["rawDataBody"] = dict(first["rawDataBody"])
    matched_data["rawDataBody"]["dataBlock"] = matched_rows
    MATCHED.write_text(
        json.dumps(matched_data, separators=(",", ":")), encoding="utf-8"
    )

    environmental = []
    for label, column in (
        ("Temperature", COL["temperature"]),
        ("Humidity", COL["humidity"]),
        ("Pressure", COL["pressure"]),
    ):
        value_1 = median(matched_rows, column)
        value_2 = median(rows_2, column)
        environmental.append(
            (label, value_1, value_2, value_2 - value_1, symmetric_deviation(value_1, value_2))
        )

    gas_steps = []
    for step in range(10):
        step_1 = [row for row in matched_rows if int(row[COL["heater_step"]]) == step]
        step_2 = [row for row in rows_2 if int(row[COL["heater_step"]]) == step]
        if not step_1 or not step_2:
            continue
        value_1 = median(step_1, COL["gas"])
        value_2 = median(step_2, COL["gas"])
        gas_steps.append((step, len(step_1), len(step_2), value_1, value_2, symmetric_deviation(value_1, value_2)))

    gas_profile_deviation = statistics.mean(row[5] for row in gas_steps)
    lines = [
        "# BME688 dataset deviation report",
        "",
        f"- Dataset 1 original rows: {len(rows_1)}",
        f"- Dataset 1 matched rows: {len(matched_rows)}",
        f"- Dataset 2 rows: {len(rows_2)}",
        "- Matching method: first contiguous Dataset 1 rows, preserving acquisition order",
        f"- Gas-profile deviation rate: **{gas_profile_deviation:.2f}%**",
        "",
        "The gas-profile rate is the mean symmetric percentage difference between the median gas resistance at each of the 10 heater steps. It measures separation, not proof of mold.",
        "",
        "## Environmental comparison",
        "",
        "| Signal | Dataset 1 median | Dataset 2 median | Difference (2-1) | Symmetric deviation |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, value_1, value_2, difference, deviation in environmental:
        lines.append(f"| {label} | {value_1:.4f} | {value_2:.4f} | {difference:.4f} | {deviation:.2f}% |")

    lines.extend([
        "",
        "## Gas profile by heater step",
        "",
        "| Heater step | Rows D1 | Rows D2 | D1 median ohms | D2 median ohms | Deviation |",
        "|---:|---:|---:|---:|---:|---:|",
    ])
    for step, count_1, count_2, value_1, value_2, deviation in gas_steps:
        lines.append(f"| {step} | {count_1} | {count_2} | {value_1:.3f} | {value_2:.3f} | {deviation:.2f}% |")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Created {MATCHED} with {len(matched_rows)} rows")
    print(f"Created {REPORT}")
    print(f"Gas-profile deviation rate: {gas_profile_deviation:.2f}%")


if __name__ == "__main__":
    main()
