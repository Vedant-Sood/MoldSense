from __future__ import annotations

import json
import hashlib
import math
import statistics
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CaptureSummary:
    name: str
    path: str
    rows: int
    cycles: int
    temperature: float
    humidity: float
    pressure: float
    gas_by_step: dict[int, float]


def bundled_directory():
    return Path(__file__).resolve().parents[1] / "baselines"


def load_capture(path):
    path = Path(path)
    document = json.loads(path.read_text(encoding="utf-8"))
    body = document["rawDataBody"]
    keys = [column["key"] for column in body["dataColumns"]]
    index = {key: position for position, key in enumerate(keys)}
    required = {"temperature", "pressure", "relative_humidity", "resistance_gassensor", "heater_profile_step_index", "scanning_cycle_index"}
    missing = required.difference(index)
    if missing:
        raise ValueError(f"Unsupported capture {path.name}; missing: {', '.join(sorted(missing))}")
    rows = [row for row in body["dataBlock"] if not row[index.get("error_code", -1)]] if "error_code" in index else body["dataBlock"]
    by_step = {}
    for row in rows:
        gas = float(row[index["resistance_gassensor"]])
        if gas > 0:
            by_step.setdefault(int(row[index["heater_profile_step_index"]]), []).append(math.log10(gas))
    name = document.get("rawDataHeader", {}).get("seedPowerOnOff") or path.stem
    return CaptureSummary(
        name=name.replace("capture_", "Cap ").title(), path=str(path), rows=len(rows),
        cycles=len({row[index["scanning_cycle_index"]] for row in rows}),
        temperature=statistics.median(float(row[index["temperature"]]) for row in rows),
        humidity=statistics.median(float(row[index["relative_humidity"]]) for row in rows),
        pressure=statistics.median(float(row[index["pressure"]]) for row in rows),
        gas_by_step={step: statistics.median(values) for step, values in by_step.items()},
    )


def bundled_references():
    return [load_capture(path) for path in sorted(bundled_directory().glob("cap_*.bmerawdata"))]


def capture_rows(path):
    """Convert an AI-Studio capture into the dashboard's graph row format."""
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    body = document["rawDataBody"]
    keys = [column["key"] for column in body["dataColumns"]]
    index = {key: position for position, key in enumerate(keys)}
    return [{
        "uptime_ms": raw[index["timestamp_since_poweron"]],
        "temperature_c": raw[index["temperature"]],
        "humidity_percent": raw[index["relative_humidity"]],
        "pressure_pa": raw[index["pressure"]],
        "gas_ohms": raw[index["resistance_gassensor"]],
        "heater_step": raw[index["heater_profile_step_index"]],
    } for raw in body["dataBlock"]]


def bundled_capture_rows():
    return {path.stem.replace("_", " ").title(): capture_rows(path) for path in sorted(bundled_directory().glob("cap_*.bmerawdata"))}


def bundled_files():
    result=[]
    for path in sorted(bundled_directory().glob("cap_*.bmerawdata")):
        payload=path.read_bytes()
        result.append((path.stem.replace("_"," ").title(),path,len(payload),hashlib.sha256(payload).hexdigest()))
    return result


def tailored_cap_comparison():
    rows=bundled_capture_rows()
    first=rows.get("Cap 1 Tailored To Cap 2", [])
    second=rows.get("Cap 2", [])
    if not first or not second:
        return None
    step_results=[]
    for step in range(10):
        one=[float(row["gas_ohms"]) for row in first if int(row["heater_step"])==step]
        two=[float(row["gas_ohms"]) for row in second if int(row["heater_step"])==step]
        if not one or not two: continue
        median_one=statistics.median(one); median_two=statistics.median(two)
        deviation=200*abs(median_two-median_one)/(abs(median_one)+abs(median_two))
        step_results.append({"step":step,"cap_1":median_one,"cap_2":median_two,"deviation":deviation})
    if not step_results:
        return None
    def median(metric,data): return statistics.median(float(row[metric]) for row in data)
    return {
        "rows":len(first), "steps":step_results,
        "gas_deviation":statistics.mean(item["deviation"] for item in step_results),
        "temperature_delta":median("temperature_c",second)-median("temperature_c",first),
        "humidity_delta":median("humidity_percent",second)-median("humidity_percent",first),
        "pressure_delta":median("pressure_pa",second)-median("pressure_pa",first),
    }


def compare_capture(reference, candidate):
    shared = sorted(set(reference.gas_by_step).intersection(candidate.gas_by_step))
    if len(shared) < 5:
        raise ValueError("Capture does not share enough heater-profile steps with the reference.")
    differences = [abs(candidate.gas_by_step[step] - reference.gas_by_step[step]) for step in shared]
    gas_change = statistics.median(differences)
    score = gas_change / 0.08
    severity = "High" if score >= 4 else "Moderate" if score >= 2 else "Similar"
    return {
        "reference": reference.name, "capture": candidate.name,
        "severity": severity, "score": score,
        "gas_ratio": 10 ** gas_change,
        "temperature_delta": candidate.temperature-reference.temperature,
        "humidity_delta": candidate.humidity-reference.humidity,
        "shared_steps": len(shared),
        "risk": "Strong heater-profile change. Investigate moisture, odors, ventilation, and repeat the measurement." if severity == "High" else "Noticeable heater-profile change. Repeat under similar conditions and review environmental causes." if severity == "Moderate" else "The heater-profile pattern is broadly similar to this reference.",
    }
