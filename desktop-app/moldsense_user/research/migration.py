"""Read-only import of legacy captures; absent measurements remain null."""

import csv, hashlib, json, math, time
from datetime import datetime, timezone
from pathlib import Path
from .database import utc

PLAUSIBLE_EPOCH = 946684800  # 2000-01-01; unset legacy clocks report 0 or uptime.


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


def _number(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _original_epoch(mapped):
    epoch = _number(mapped.get("unix_epoch"))
    if epoch is not None and epoch >= PLAUSIBLE_EPOCH:
        return epoch
    text = str(mapped.get("iso_utc") or mapped.get("timestamp") or "").strip()
    if text and text != "UNSET":
        try:
            stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.timestamp()
    return None


def time_basis(path):
    """One basis per file so a clock set part-way through cannot reorder rows."""
    utc_rows = uptime_rows = total = 0
    for mapped, _raw in legacy_rows(path):
        total += 1
        utc_rows += _original_epoch(mapped) is not None
        uptime_rows += _number(mapped.get("uptime_ms")) is not None
    if total and utc_rows == total:
        return "DEVICE_UTC"
    if total and uptime_rows == total:
        return "UPTIME_RELATIVE_TO_IMPORT"
    return "ROW_INDEX_SECONDS"


class LegacyClock:
    """Ordering time for imported rows on a single time basis."""

    def __init__(self, anchor, basis):
        self.anchor = anchor
        self.basis = basis
        self.previous = None
        self.base = 0.0
        self.segment_start = None
        self.last_uptime = None

    def __call__(self, mapped, index):
        if self.basis == "DEVICE_UTC":
            epoch = _original_epoch(mapped)
        elif self.basis == "UPTIME_RELATIVE_TO_IMPORT":
            uptime = _number(mapped.get("uptime_ms"))
            if self.segment_start is None or uptime < self.last_uptime:
                # First row, or uptime restarted: continue after the previous row.
                self.base = 0.0 if self.previous is None else self.previous + 1 - self.anchor
                self.segment_start = uptime
            self.last_uptime = uptime
            epoch = self.anchor + self.base + (uptime - self.segment_start) / 1000
        else:
            epoch = self.anchor + index
        if self.previous is not None and epoch <= self.previous:
            epoch = self.previous + 0.001
        self.previous = epoch
        return epoch


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
    try:
        archive = db.root / "legacy_sources"
        archive.mkdir(exist_ok=True)
        (archive / (digest + path.suffix)).write_bytes(payload)
        frames = []
        clock = LegacyClock(time.time(), time_basis(path))
        from .database import FIELDS

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
            for field in FIELDS + ["uptime_ms"]:
                try:
                    value = float(mapped[field])
                    packet[field] = value if math.isfinite(value) else None
                except (KeyError, ValueError, TypeError):
                    pass
            packet["uptime_ms"] = (
                int(packet["uptime_ms"]) if packet.get("uptime_ms") is not None else None
            )
            packet["original_uptime_available"] = "uptime_ms" in mapped
            # received_at is import time; received_epoch orders rows on their original
            # time basis so plots and time ranges keep their shape. Originals stay in raw_json.
            frames.append((json.dumps(raw), packet, None, utc(), clock(mapped, index)))
            if len(frames) >= 500:
                db.ingest_batch(session, frames)
                frames = []
        if frames:
            db.ingest_batch(session, frames)
        db.event(session, "LEGACY_TIME_BASIS", {"basis": clock.basis})
        db.session_state(session, "stopped")
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO imports VALUES(?,?,?,?)", (digest, str(path), session, utc())
            )
    except BaseException:
        # Leave no half-imported session behind, so a retry starts clean.
        location = db.rows("SELECT location_id FROM samples WHERE id=?", (sample,))
        with db.transaction() as conn:
            for table in ("readings", "packets", "events", "calibrations", "annotations"):
                conn.execute(f"DELETE FROM {table} WHERE session_id=?", (session,))
            conn.execute("DELETE FROM sessions WHERE id=?", (session,))
            conn.execute("DELETE FROM samples WHERE id=?", (sample,))
            if location:
                conn.execute(
                    "DELETE FROM locations WHERE id=? AND id NOT IN (SELECT location_id FROM samples WHERE location_id IS NOT NULL)",
                    (location[0]["location_id"],),
                )
        raise
    return session


def import_archives(db, legacy_store):
    result = []
    for row in legacy_store.imports():
        path = Path(row[4])
        if path.is_file() and path.suffix.lower() in (".csv", ".bmerawdata"):
            result.append(import_legacy(db, path))
    return result
