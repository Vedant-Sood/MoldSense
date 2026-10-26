"""Read-only import of legacy captures; absent measurements remain null."""

import csv, hashlib, json, math, time
from pathlib import Path
from .database import utc


def legacy_rows(path):
    path = Path(path)
    if path.suffix.lower() == ".bmerawdata":
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
        body = doc["rawDataBody"]
        keys = [x["key"] for x in body["dataColumns"]]
        aliases = {
            "timestamp_since_poweron": "uptime_ms",
            "temperature": "temperature_c",
            "relative_humidity": "humidity_percent",
            "pressure": "pressure_pa",
            "resistance_gassensor": "gas_resistance_ohms",
            "heater_profile_step_index": "gas_heater_index",
        }
        for values in body["dataBlock"]:
            raw = dict(zip(keys, values))
            yield {aliases.get(k, k): v for k, v in raw.items()}, raw
    else:
        with path.open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                mapped = dict(row)
                for old, new in {
                    "gas_ohms": "gas_resistance_ohms",
                    "comp_temperature_c": "temperature_c",
                    "comp_humidity_percent": "humidity_percent",
                    "wallRaw": "wall_cap_raw",
                    "wallFiltered": "wall_cap_filtered",
                    "wallMoistureIndex": "wall_moisture_index",
                    "heater_step": "gas_heater_index",
                }.items():
                    if new not in mapped and old in mapped:
                        mapped[new] = mapped[old]
                yield mapped, row


def import_legacy(db, path, experiment=None):
    path = Path(path)
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    existing = db.rows("SELECT session_id FROM imports WHERE sha256=?", (digest,))
    if existing:
        return existing[0]["session_id"]
    experiment = experiment or db.create_experiment("Legacy imports")
    sample = db.create_sample(path.stem, "Unknown legacy location", label="UNKNOWN")
    from .statistics import DEFAULT_SETTINGS

    session = db.create_session(
        experiment,
        sample,
        path.stem,
        "LEGACY_UNKNOWN",
        {
            "source_path": str(path),
            "sha256": digest,
            "original_time_basis": "unknown unless present",
            "gas_profile": "LEGACY_REQUIRES_VERIFICATION",
        },
        DEFAULT_SETTINGS,
        "legacy",
    )
    archive = db.root / "legacy_sources"
    archive.mkdir(exist_ok=True)
    (archive / (digest + path.suffix)).write_bytes(payload)
    frames = []
    epoch = time.time()
    for index, (mapped, raw) in enumerate(legacy_rows(path)):
        packet = {
            "type": "reading",
            "protocol_version": 1,
            "device_id": "LEGACY_UNKNOWN",
            "firmware_version": "UNKNOWN",
            "boot_id": digest[:16],
            "sequence": index,
            "uptime_ms": None,
            "source": "legacy",
            "data_quality": "LEGACY_INCOMPLETE",
            "legacy_original": raw,
        }
        from .database import FIELDS

        for field in FIELDS + ["uptime_ms"]:
            try:
                value = float(mapped[field])
                packet[field] = value if math.isfinite(value) else None
            except (KeyError, ValueError, TypeError):
                pass
        # Import time is receipt time; original timestamps are retained verbatim in raw_json.
        packet["uptime_ms"] = (
            int(packet["uptime_ms"]) if packet.get("uptime_ms") is not None else None
        )
        packet["original_uptime_available"] = "uptime_ms" in mapped
        frames.append((json.dumps(raw), packet, None, utc(), epoch))
        if len(frames) >= 500:
            db.ingest_batch(session, frames)
            frames = []
    if frames:
        db.ingest_batch(session, frames)
    db.session_state(session, "stopped")
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO imports VALUES(?,?,?,?)", (digest, str(path), session, utc())
        )
    return session


def import_archives(db, legacy_store):
    result = []
    for row in legacy_store.imports():
        path = Path(row[4])
        if path.is_file() and path.suffix.lower() in (".csv", ".bmerawdata"):
            result.append(import_legacy(db, path))
    return result
