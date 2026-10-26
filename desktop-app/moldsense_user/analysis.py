from __future__ import annotations

import math, statistics
from dataclasses import dataclass
from datetime import datetime, timezone

METRICS = {"iaq": ("IAQ", "index"), "temperature_c": ("Temperature", "°C"), "humidity_percent": ("Humidity", "%"), "pressure_pa": ("Pressure", "hPa"), "gas_ohms": ("Gas resistance", "Ω")}

@dataclass(frozen=True)
class Deviation:
    start: str; end: str; severity: str; score: float; metric: str
    value: float; baseline: float; explanation: str; risk: str

def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError): return None

def timestamp(row, index=0):
    text = str(row.get("iso_utc") or row.get("timestamp") or "")
    if text and text != "UNSET": return text
    epoch = number(row.get("unix_epoch"))
    if epoch and epoch > 0: return datetime.fromtimestamp(epoch, timezone.utc).isoformat()
    return f"Device time +{int((number(row.get('uptime_ms')) or index * 60000) / 1000)}s"

def metric_value(row, metric):
    aliases = {"temperature_c": ("temperature_c", "comp_temperature_c", "raw_temperature_c"), "humidity_percent": ("humidity_percent", "comp_humidity_percent", "raw_humidity_percent"), "pressure_pa": ("pressure_pa", "raw_pressure_pa"), "gas_ohms": ("gas_ohms", "raw_gas_ohms")}
    for key in aliases.get(metric, (metric,)):
        value = number(row.get(key))
        if value is not None: return value / 100 if metric == "pressure_pa" and value > 2000 else value
    return None

def build_baseline(rows):
    result = {}
    for metric in METRICS:
        values = [v for row in rows if (v := metric_value(row, metric)) is not None]
        if len(values) >= 5:
            median = statistics.median(values)
            result[metric] = {"median": median, "mad": statistics.median(abs(v-median) for v in values), "count": len(values)}
    return result

def _risk(metric, value):
    if metric == "humidity_percent": return "Sustained high humidity can support condensation and mold growth. Inspect moisture sources and ventilation." if value >= 70 else "Humidity changed from the room baseline. Check ventilation, occupancy, and moisture."
    if metric == "iaq": return "Air-quality conditions changed materially. Ventilate and investigate odors, chemicals, smoke, or dampness."
    if metric == "gas_ohms": return "Gas resistance shifted, which may reflect volatile compounds. This sensor cannot identify a specific substance."
    if metric == "temperature_c": return "Temperature changed enough to affect comfort and sensor response. Check HVAC, sunlight, and placement."
    return "Pressure changed unusually; weather or elevation changes are common causes."

def analyze(rows, baseline, threshold=3.5):
    hits, floors = [], {"iaq": 5, "temperature_c": .35, "humidity_percent": 2, "pressure_pa": 1, "gas_ohms": 5000}
    for index, row in enumerate(rows):
        for metric, stats in baseline.items():
            value = metric_value(row, metric)
            if value is None: continue
            score = abs(value-stats["median"]) / max(stats.get("mad", 0)*1.4826, floors[metric])
            if score < threshold: continue
            severity = "High" if score >= 7 or (metric == "humidity_percent" and value >= 75) else "Moderate"
            label, unit = METRICS[metric]
            quality = " IAQ accuracy was low, so confidence is reduced." if metric == "iaq" and (number(row.get("iaq_accuracy")) or 0) < 2 else ""
            hits.append((index,Deviation(timestamp(row,index), timestamp(row,index), severity, score, metric, value, stats["median"], f"{label} was {value:.2f} {unit}, {value-stats['median']:+.2f} from baseline.{quality}", _risk(metric,value))))
    periods=[]
    for metric in METRICS:
        last_index=-2
        for index,hit in (x for x in hits if x[1].metric==metric):
            if periods and periods[-1][1].metric==metric and periods[-1][1].severity==hit.severity and index==last_index+1:
                old=periods[-1][1]
                periods[-1]=(periods[-1][0],Deviation(old.start,hit.end,old.severity,max(old.score,hit.score),old.metric,hit.value,old.baseline,hit.explanation,hit.risk))
            else: periods.append((index,hit))
            last_index=index
    return [hit for _index,hit in sorted(periods,key=lambda x:x[0])]

def overall_risk(items):
    if any(x.severity == "High" for x in items): return "HIGH", "A strong deviation was detected. Ventilate, check moisture/odors, and inspect the marked period."
    if items: return "WATCH", "Conditions departed from baseline. Review marked periods and repeat the test if the cause is unclear."
    return "NORMAL", "No significant departure from the saved baseline was found."
