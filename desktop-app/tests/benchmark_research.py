"""Reproducible million-reading SQLite benchmark; disposable synthetic data only."""

import json, sys, tempfile, time, math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from moldsense_user.research.database import Database, utc
from moldsense_user.research.statistics import DEFAULT_SETTINGS, analyze_database

count = int(sys.argv[1]) if len(sys.argv) > 1 else 1000000
parent = Path(__file__).resolve().parents[2] / "outputs/research_benchmark"
parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(dir=parent) as folder:
    db = Database(folder)
    exp = db.create_experiment("SYNTHETIC BENCHMARK")
    sample = db.create_sample("SYNTHETIC", "SYNTHETIC")
    session = db.create_session(
        exp, sample, "SYNTHETIC", "TEST", {}, DEFAULT_SETTINGS, "synthetic"
    )
    start = time.monotonic()
    stamp = utc()
    for base in range(0, count, 2000):
        frames = []
        for i in range(base, min(count, base + 2000)):
            p = {
                "type": "reading",
                "protocol_version": 1,
                "device_id": "TEST",
                "firmware_version": "1.0.0-rc1",
                "boot_id": "synthetic",
                "sequence": i,
                "uptime_ms": i * 1000,
                "wall_cap_raw": 100 + i % 7,
                "wall_cap_filtered": 100 + i % 7,
                "wall_moisture_index": i % 20,
                "gas_resistance_ohms": 400000 + i % 1000,
                "gas_observation_id": i,
                "gas_heater_index": 0,
                "temperature_c": 25,
                "humidity_percent": 50,
                "data_quality": "VALID",
                "source": "synthetic",
            }
            frames.append((json.dumps(p), p, None, stamp, 1700000000 + i))
        db.ingest_batch(session, frames)
        if base and base % 100000 == 0:
            print("Inserted", base, "rows", flush=True)
    insert_seconds = time.monotonic() - start
    assert db.count(session) == count
    start = time.monotonic()
    page = db.query([session], limit=250, offset=count - 250)
    page_seconds = time.monotonic() - start
    assert len(page) == 250
    start = time.monotonic()
    plot = db.plot_rows(session, limit=2400)
    plot_seconds = time.monotonic() - start
    assert len(plot) <= 2410
    start = time.monotonic()
    summary = analyze_database(db, [session])
    statistics_seconds = time.monotonic() - start
    assert summary["wall"]["n"] == count
    result = {
        "rows": count,
        "insert_seconds": insert_seconds,
        "last_page_seconds": page_seconds,
        "plot_query_seconds": plot_seconds,
        "plot_points": len(plot),
        "exact_statistics_seconds": statistics_seconds,
        "database_bytes": db.path.stat().st_size,
        "wall_mean": summary["wall"]["mean"],
    }
    print(json.dumps(result, indent=2), flush=True)
    output = (
        Path(__file__).resolve().parents[2]
        / "outputs/moldsense_research_qa/benchmark.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2))
    db.close()
