"""Traceable data exports and local research reports."""

import csv, hashlib, html, json
from pathlib import Path
from .database import FIELDS, utc
from .statistics import analyze_database, DEFAULT_SETTINGS
from .plots import time_figure


def export_data(db, sessions, path, kind="raw", start=None, end=None, variables=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "exported_at": utc(),
        "kind": kind,
        "range_utc_epoch": [start, end],
        "sessions": [db.metadata(s) for s in sessions],
        "raw_data_unchanged": True,
    }
    if kind == "json":
        with path.open("w", encoding="utf-8") as handle:
            handle.write(
                '{"metadata":' + json.dumps(metadata, allow_nan=False) + ',"readings":['
            )
            first = True
            for row in db.iter_readings(sessions, start, end):
                if not first:
                    handle.write(",")
                handle.write(json.dumps(row, allow_nan=False))
                first = False
            handle.write('],"packets":[')
            first = True
            for session in sessions:
                last = 0
                maximum = (
                    db.rows(
                        "SELECT MAX(id) hi FROM packets WHERE session_id=?", (session,)
                    )[0]["hi"]
                    or 0
                )
                while True:
                    rows = db.rows(
                        "SELECT * FROM packets WHERE session_id=? AND id>? AND id<=? ORDER BY id LIMIT 2000",
                        (session, last, maximum),
                    )
                    if not rows:
                        break
                    for row in rows:
                        if not first:
                            handle.write(",")
                        handle.write(json.dumps(row, allow_nan=False))
                        first = False
                    last = rows[-1]["id"]
            handle.write("]}")
    else:
        selected = [v for v in (variables or FIELDS) if v in FIELDS]
        identity = [
            "id",
            "experiment_id",
            "session_id",
            "sample_id",
            "location_id",
            "ground_truth",
            "device_id",
            "firmware_version",
            "software_version",
            "model_version",
            "calibration_id",
            "analysis_config_id",
            "boot_id",
            "sequence",
            "received_at",
            "received_epoch",
            "uptime_ms",
            "quality",
            "source",
        ]
        fields = identity + selected + (["raw_json"] if kind == "raw" else [])
        by_id = {s["id"]: s for s in metadata["sessions"]}
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in db.iter_readings(sessions, start, end):
                meta = by_id[row["session_id"]]
                params = meta["parameters"]
                packet = json.loads(row["raw_json"])
                row.update(
                    {
                        "experiment_id": meta["experiment_id"],
                        "sample_id": meta["sample_id"],
                        "location_id": params.get("location_id"),
                        "ground_truth": meta["ground_truth"],
                        "firmware_version": packet.get("firmware_version"),
                        "software_version": params.get("desktop_version"),
                        "model_version": packet.get("model_sha256"),
                        "calibration_id": packet.get("baseline_id"),
                        "analysis_config_id": meta["analysis_config_id"],
                    }
                )
                writer.writerow(row)
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    metadata["sha256"] = digest.hexdigest()
    path.with_suffix(path.suffix + ".metadata.json").write_text(
        json.dumps(metadata, indent=2, allow_nan=False), encoding="utf-8"
    )
    return path


def save_figure(figure, path, metadata):
    path = Path(path)
    figure.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    path.with_suffix(path.suffix + ".metadata.json").write_text(
        json.dumps(metadata, indent=2, allow_nan=False), encoding="utf-8"
    )
    return path


def session_report(db, session, folder, settings=None, reference=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    meta = db.metadata(session)
    settings = settings or DEFAULT_SETTINGS
    wall_field = settings.get("wall_field", "wall_cap_filtered")
    meta["report_analysis_settings"] = settings
    meta["control_reference_means"] = reference
    summary = analyze_database(
        db, [session], wall_field, settings=settings, reference=reference
    )
    rows = db.plot_rows(session)
    fig, _ = time_figure(rows, meta, summary, wall_field, reference=reference)
    save_figure(fig, folder / "signals.png", meta)
    save_figure(fig, folder / "signals.svg", meta)
    esc = lambda value: html.escape(str(value))
    stats_rows = "".join(
        "<tr><td>"
        + esc(key)
        + "</td><td>"
        + esc(summary["wall"].get(key))
        + "</td><td>"
        + esc(summary["gas"].get(key))
        + "</td></tr>"
        for key in summary["wall"]
    )
    notes = "".join(
        "<li>" + esc(n["created_at"]) + " — " + esc(n["text"]) + "</li>"
        for n in meta["annotations"]
    )
    document = '<!doctype html><html><meta charset="utf-8"><title>MoldSense session report</title><style>body{font:15px system-ui;max-width:1100px;margin:40px auto;color:#22322f}h1,h2{color:#176b62}table{border-collapse:collapse;width:100%}td,th{padding:9px;border-bottom:1px solid #ddd;text-align:left}pre{white-space:pre-wrap;font:12px monospace}img{width:100%}</style><h1>MoldSense research session</h1>'
    document += (
        "<p>"
        + esc(meta["experiment_name"])
        + " / "
        + esc(meta["sample_name"])
        + " / "
        + esc(meta["location_name"])
        + "</p><p>Ground truth: <b>"
        + esc(meta["ground_truth"])
        + "</b>. Firmware predictions remain separate.</p>"
    )
    document += (
        "<p>Readings: "
        + str(summary["total_rows"])
        + "; excluded by quality policy: "
        + str(summary["excluded_rows"])
        + ". Gas heater step: "
        + esc(settings.get("gas_heater_index"))
        + '.</p><img src="signals.png" alt="Wall and gas signals"><h2>Full-data statistics</h2><table><tr><th>Statistic</th><th>Wall response</th><th>Gas resistance (Ω)</th></tr>'
        + stats_rows
        + "</table><h2>Correlation</h2><pre>"
        + esc(json.dumps(summary["correlation"], indent=2))
        + "</pre>"
    )
    document += (
        "<p>Neither gas-resistance change nor the screening index proves mold. Material, geometry, heater profile, ambient conditions, and independent ground truth must be considered.</p><h2>Annotations</h2><ul>"
        + notes
        + "</ul><h2>Environment</h2><pre>"
        + esc(
            json.dumps({k: summary[k] for k in ("temperature", "humidity")}, indent=2)
        )
        + "</pre><h2>Calibration and reproducibility metadata</h2><pre>"
        + esc(json.dumps(meta, indent=2))
        + "</pre></html>"
    )
    path = folder / "report.html"
    path.write_text(document, encoding="utf-8")
    (folder / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8"
    )
    config = db.analysis_config(settings)
    with db.transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO summaries VALUES(?,?,?,?)",
            (session, utc(), config, json.dumps(summary, allow_nan=False)),
        )
    return path
