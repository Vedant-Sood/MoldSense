"""Descriptive statistics on full selected data, never on plot downsampling."""

from collections import deque
import math
import numpy as np
from scipy import stats

DEFAULT_SETTINGS = {
    "version": "1.0",
    "rolling_window": 30,
    "outlier_method": "MAD_ADVISORY",
    "include_flagged": False,
    "gas_heater_index": 0,
    "deduplicate_gas_observations": True,
    "confidence_interval_unit": "independent session means",
}


def percent(value, reference):
    return (
        100 * (value - reference) / abs(reference)
        if value is not None and reference not in (None, 0)
        else None
    )


def describe(values, reference=None):
    x = np.array(
        [float(v) for v in values if v is not None and math.isfinite(v)], dtype=float
    )
    n = len(x)
    if not n:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "min": None,
            "max": None,
            "range": None,
            "sd": None,
            "variance": None,
            "cv_percent": None,
            "difference": None,
            "percent_difference": None,
            "q1": None,
            "q3": None,
            "mad_flagged": 0,
        }
    mean = float(x.mean())
    sd = float(x.std(ddof=1)) if n > 1 else None
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med)))
    return {
        "n": n,
        "mean": mean,
        "median": med,
        "min": float(x.min()),
        "max": float(x.max()),
        "range": float(np.ptp(x)),
        "sd": sd,
        "variance": sd * sd if sd is not None else None,
        "cv_percent": 100 * sd / abs(mean) if sd is not None and mean else None,
        "difference": mean - reference if reference is not None else None,
        "percent_difference": percent(mean, reference),
        "q1": float(np.percentile(x, 25)),
        "q3": float(np.percentile(x, 75)),
        "mad_flagged": int((np.abs(x - med) > 3 * 1.4826 * mad).sum()) if mad else 0,
    }


def valid_row(row, include_flagged=False):
    return include_flagged or row.get("quality", "VALID") in ("VALID", "WARMING_UP")


def pair_values(rows, wall_field="wall_cap_filtered", include_flagged=False, heater=0):
    x = []
    y = []
    seen = set()
    for row in rows:
        if not valid_row(row, include_flagged):
            continue
        if heater is not None and row.get("gas_heater_index") not in (None, heater):
            continue
        a = row.get(wall_field)
        b = row.get("gas_resistance_ohms")
        if a is None or b is None or not math.isfinite(a) or not math.isfinite(b):
            continue
        observation = row.get("gas_observation_id")
        key = (row.get("session_id"), row.get("boot_id"), observation)
        if observation is not None and key in seen:
            continue
        if observation is not None:
            seen.add(key)
        x.append(a)
        y.append(b)
    return np.array(x), np.array(y)


def correlation(x, y):
    n = len(x)
    warning = "Descriptive association only; time-series samples are autocorrelated. No causation or independence assumed."
    if n < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return {
            "n": n,
            "pearson": None,
            "spearman": None,
            "warning": "Insufficient paired data or constant signal. " + warning,
        }
    return {
        "n": n,
        "pearson": float(stats.pearsonr(x, y).statistic),
        "spearman": float(stats.spearmanr(x, y).statistic),
        "warning": warning,
    }


def rolling(values, window=30):
    q = deque(maxlen=max(1, window))
    result = []
    for value in values:
        if value is None or not math.isfinite(value):
            q.clear()
            result.append(float("nan"))
            continue
        q.append(value)
        result.append(sum(q) / len(q))
    return result


def analyze(rows, wall_field="wall_cap_filtered", reference=None, settings=None):
    settings = settings or DEFAULT_SETTINGS
    reference = reference or {}
    include = settings.get("include_flagged", False)
    heater = settings.get("gas_heater_index", 0)
    good = [r for r in rows if valid_row(r, include)]
    x, y = pair_values(rows, wall_field, include, heater)
    # Wall statistics use each stored wall observation; gas stats count fresh gas observations.
    gas_rows = []
    seen = set()
    for r in good:
        if heater is not None and r.get("gas_heater_index") not in (None, heater):
            continue
        key = (r.get("session_id"), r.get("boot_id"), r.get("gas_observation_id"))
        if r.get("gas_observation_id") is not None and key in seen:
            continue
        seen.add(key)
        gas_rows.append(r)
    return {
        "wall": describe([r.get(wall_field) for r in good], reference.get("wall")),
        "gas": describe(
            [r.get("gas_resistance_ohms") for r in gas_rows], reference.get("gas")
        ),
        "temperature": describe([r.get("temperature_c") for r in good]),
        "humidity": describe([r.get("humidity_percent") for r in good]),
        "correlation": correlation(x, y),
        "total_rows": len(rows),
        "excluded_rows": len(rows) - len(good),
        "wall_field": wall_field,
        "gas_heater_index": heater,
        "notice": "MAD flags are advisory and never delete real events. No per-reading 95% CI is reported because samples are serially correlated.",
    }


def independent_ci(session_means):
    x = np.asarray(session_means, dtype=float)
    if len(x) < 3:
        return None
    half = float(stats.t.ppf(0.975, len(x) - 1) * stats.sem(x))
    return [float(x.mean() - half), float(x.mean() + half)]


def effect_size(control, test):
    a = np.asarray(control, dtype=float)
    b = np.asarray(test, dtype=float)
    if min(len(a), len(b)) < 2:
        return None
    pooled = math.sqrt(
        ((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1))
        / (len(a) + len(b) - 2)
    )
    return float((b.mean() - a.mean()) / pooled) if pooled else None


def analyze_database(
    db,
    sessions,
    wall_field="wall_cap_filtered",
    reference=None,
    settings=None,
    start=None,
    end=None,
):
    """Bounded row batches plus compact numeric arrays for exact quantiles."""
    from array import array

    settings = settings or DEFAULT_SETTINGS
    reference = reference or {}
    include = settings.get("include_flagged", False)
    heater = settings.get("gas_heater_index", 0)
    wall = array("d")
    gas = array("d")
    temperature = array("d")
    humidity = array("d")
    risk = array("d")
    px = array("d")
    py = array("d")
    last = {}
    total = excluded = 0
    for row in db.iter_analysis(sessions, wall_field, start, end):
        total += 1
        if not valid_row(row, include):
            excluded += 1
            continue
        for key, dest in (
            (wall_field, wall),
            ("temperature_c", temperature),
            ("humidity_percent", humidity),
            ("mold_probability", risk),
        ):
            value = row.get(key)
            if value is not None and math.isfinite(value):
                dest.append(value)
        if heater is not None and row.get("gas_heater_index") not in (None, heater):
            continue
        identity = (row["session_id"], row["boot_id"])
        observation = row.get("gas_observation_id")
        if observation is not None and last.get(identity) == observation:
            continue
        last[identity] = observation
        value = row.get("gas_resistance_ohms")
        if value is not None and math.isfinite(value):
            gas.append(value)
            if row.get(wall_field) is not None:
                px.append(row[wall_field])
                py.append(value)
    return {
        "wall": describe(wall, reference.get("wall")),
        "gas": describe(gas, reference.get("gas")),
        "temperature": describe(temperature),
        "humidity": describe(humidity),
        "risk": describe(risk),
        "correlation": correlation(np.asarray(px), np.asarray(py)),
        "total_rows": total,
        "excluded_rows": excluded,
        "wall_field": wall_field,
        "gas_heater_index": heater,
        "notice": "Exact selected-data statistics. CI requires independent replicate sessions; MAD flags are advisory.",
    }


def distributions_database(
    db, sessions, wall_field="wall_cap_filtered", settings=None, start=None, end=None
):
    from array import array

    settings = settings or DEFAULT_SETTINGS
    values = {wall_field: array("d"), "gas_resistance_ohms": array("d")}
    last = {}
    for row in db.iter_analysis(sessions, wall_field, start, end):
        if not valid_row(row, settings.get("include_flagged", False)):
            continue
        v = row.get(wall_field)
        if v is not None and math.isfinite(v):
            values[wall_field].append(v)
        if row.get("gas_heater_index") not in (
            None,
            settings.get("gas_heater_index", 0),
        ):
            continue
        key = (row["session_id"], row["boot_id"])
        obs = row.get("gas_observation_id")
        if obs is not None and last.get(key) == obs:
            continue
        last[key] = obs
        v = row.get("gas_resistance_ohms")
        if v is not None and math.isfinite(v):
            values["gas_resistance_ohms"].append(v)
    result = {}
    for field, buffer in values.items():
        a = np.asarray(buffer)
        if not len(a):
            result[field] = {"n": 0}
            continue
        q1, med, q3 = np.percentile(a, [25, 50, 75])
        iqr = q3 - q1
        lo = q1 - 1.5 * iqr
        hi = q3 + 1.5 * iqr
        fliers = a[(a < lo) | (a > hi)]
        inside = a[(a >= lo) & (a <= hi)]
        counts, edges = np.histogram(a, bins=30)
        result[field] = {
            "n": len(a),
            "counts": counts.tolist(),
            "edges": edges.tolist(),
            "outlier_count": len(fliers),
            "box": {
                "q1": float(q1),
                "med": float(med),
                "q3": float(q3),
                "whislo": float(inside.min()),
                "whishi": float(inside.max()),
                "fliers": fliers[:: max(1, (len(fliers) + 1999) // 2000)].tolist(),
            },
        }
    return result
