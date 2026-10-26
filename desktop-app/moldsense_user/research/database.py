"""SQLite source-of-truth; original packets/measurements are immutable."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib, json, math, sqlite3, threading, time, uuid
from pathlib import Path
from ..storage import data_root
from . import VERSION

FIELDS = [
    "wall_cap_raw",
    "wall_cap_filtered",
    "wall_moisture_index",
    "wall_baseline",
    "wall_deviation",
    "gas_resistance_ohms",
    "temperature_c",
    "humidity_percent",
    "pressure_pa",
    "iaq",
    "static_iaq",
    "iaq_accuracy",
    "stabilization_status",
    "run_in_status",
    "dew_point_c",
    "mold_probability",
    "confidence",
    "gas_rolling_mean",
    "gas_deviation",
    "gas_observation_id",
    "gas_heater_index",
    "wall_rolling_mean",
    "wall_raw_rolling_mean",
    "wall_index_rolling_mean",
]
LABELS = [
    "UNKNOWN",
    "CONTROL",
    "DRY",
    "DAMP",
    "VISIBLE_MOLD",
    "CONFIRMED_MOLD",
    "POST_TREATMENT",
    "OTHER",
]


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def uid():
    return uuid.uuid4().hex


def quality(packet):
    flags = []
    reported = packet.get("data_quality", "VALID")
    if reported != "VALID":
        flags.append(reported)
    limits = {
        "humidity_percent": (0, 100),
        "temperature_c": (-40, 85),
        "pressure_pa": (30000, 110000),
        "gas_resistance_ohms": (0, 1e10),
        "wall_moisture_index": (0, 100),
        "confidence": (0, 100),
        "mold_probability": (0, 100),
    }
    for key, (lo, hi) in limits.items():
        value = packet.get(key)
        if value is not None and (not math.isfinite(value) or not lo <= value <= hi):
            flags.append("IMPLAUSIBLE_" + key)
    if packet.get("wall_valid") is False:
        flags.append("WALL_INVALID")
    if packet.get("air_valid") is False:
        flags.append("AIR_INVALID")
    return list(dict.fromkeys(flags)) or ["VALID"]


class Database:
    def __init__(self, root=None):
        self.root = Path(root) if root else data_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "research.sqlite3"
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=10000")
        columns = ",".join(f"{field} REAL" for field in FIELDS)
        self.db.executescript(
            f"""
        CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
        INSERT OR IGNORE INTO schema_version VALUES(1);
        CREATE TABLE IF NOT EXISTS experiments(id TEXT PRIMARY KEY,name TEXT NOT NULL,created_at TEXT,notes TEXT);
        CREATE TABLE IF NOT EXISTS locations(id TEXT PRIMARY KEY,name TEXT,room TEXT,material TEXT,description TEXT);
        CREATE TABLE IF NOT EXISTS samples(id TEXT PRIMARY KEY,name TEXT,location_id TEXT REFERENCES locations(id),ground_truth TEXT NOT NULL DEFAULT 'UNKNOWN',notes TEXT);
        CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY,info_json TEXT,seen_at TEXT);
        CREATE TABLE IF NOT EXISTS firmware_versions(id TEXT PRIMARY KEY,metadata_json TEXT);
        CREATE TABLE IF NOT EXISTS model_versions(id TEXT PRIMARY KEY,metadata_json TEXT);
        CREATE TABLE IF NOT EXISTS analysis_configs(id TEXT PRIMARY KEY,created_at TEXT,settings_json TEXT);
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,experiment_id TEXT REFERENCES experiments(id),sample_id TEXT REFERENCES samples(id),name TEXT,device_id TEXT,state TEXT,started_at TEXT,ended_at TEXT,parameters_json TEXT,analysis_config_id TEXT REFERENCES analysis_configs(id),source TEXT DEFAULT 'live');
        CREATE TABLE IF NOT EXISTS packets(id INTEGER PRIMARY KEY,session_id TEXT,received_at TEXT,received_epoch REAL,raw TEXT,error TEXT);
        CREATE TABLE IF NOT EXISTS readings(id INTEGER PRIMARY KEY,session_id TEXT REFERENCES sessions(id),device_id TEXT,boot_id TEXT,sequence INTEGER,received_at TEXT,received_epoch REAL,uptime_ms INTEGER,quality TEXT,source TEXT,raw_json TEXT,{columns},UNIQUE(session_id,device_id,boot_id,sequence));
        CREATE INDEX IF NOT EXISTS reading_time ON readings(session_id,received_epoch,id);
        CREATE INDEX IF NOT EXISTS reading_session_id ON readings(session_id,id);
        CREATE INDEX IF NOT EXISTS reading_quality ON readings(session_id,quality);
        CREATE INDEX IF NOT EXISTS packet_session ON packets(session_id,id);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,session_id TEXT,created_at TEXT,epoch REAL,kind TEXT,payload_json TEXT);
        CREATE TABLE IF NOT EXISTS calibrations(id INTEGER PRIMARY KEY,device_id TEXT,session_id TEXT,created_at TEXT,firmware_baseline_id TEXT,payload_json TEXT);
        CREATE TABLE IF NOT EXISTS annotations(id TEXT PRIMARY KEY,session_id TEXT REFERENCES sessions(id),created_at TEXT,epoch REAL,reading_id INTEGER,text TEXT);
        CREATE TABLE IF NOT EXISTS imports(sha256 TEXT PRIMARY KEY,source_path TEXT,session_id TEXT,imported_at TEXT);
        CREATE TABLE IF NOT EXISTS summaries(session_id TEXT PRIMARY KEY,generated_at TEXT,analysis_config_id TEXT,payload_json TEXT);
        """
        )
        existing = {row[1] for row in self.db.execute("PRAGMA table_info(readings)")}
        for field in FIELDS:
            if field not in existing:
                self.db.execute(f"ALTER TABLE readings ADD COLUMN {field} REAL")
        self.db.commit()

    @contextmanager
    def transaction(self):
        with self.lock:
            try:
                yield self.db
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise

    def rows(self, sql, args=()):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in connection.execute(sql, args)]
        finally:
            connection.close()

    def event(self, session, kind, payload):
        with self.transaction() as db:
            db.execute(
                "INSERT INTO events(session_id,created_at,epoch,kind,payload_json) VALUES(?,?,?,?,?)",
                (
                    session,
                    utc(),
                    time.time(),
                    kind,
                    json.dumps(payload, allow_nan=False),
                ),
            )

    def create_experiment(self, name, notes=""):
        ident = uid()
        with self.transaction() as db:
            db.execute(
                "INSERT INTO experiments VALUES(?,?,?,?)", (ident, name, utc(), notes)
            )
        return ident

    def create_sample(
        self,
        name,
        location,
        room="",
        material="",
        description="",
        label="UNKNOWN",
        notes="",
    ):
        location_id = (
            location
            if self.rows("SELECT id FROM locations WHERE id=?", (location,))
            else uid()
        )
        ident = uid()
        with self.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO locations VALUES(?,?,?,?,?)",
                (location_id, location, room, material, description),
            )
            db.execute(
                "INSERT INTO samples VALUES(?,?,?,?,?)",
                (ident, name, location_id, label or "UNKNOWN", notes),
            )
        return ident

    def analysis_config(self, settings):
        raw = json.dumps(settings, sort_keys=True, allow_nan=False)
        ident = hashlib.sha256(raw.encode()).hexdigest()[:16]
        with self.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO analysis_configs VALUES(?,?,?)",
                (ident, utc(), raw),
            )
        return ident

    def create_session(
        self, experiment, sample, name, device, parameters, settings, source="live"
    ):
        ident = uid()
        config = self.analysis_config(settings)
        parameters = {**parameters, "desktop_version": VERSION}
        with self.transaction() as db:
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ident,
                    experiment,
                    sample,
                    name,
                    device,
                    "recording",
                    utc(),
                    None,
                    json.dumps(parameters, allow_nan=False),
                    config,
                    source,
                ),
            )
        return ident

    def session_state(self, ident, state):
        with self.transaction() as db:
            db.execute(
                "UPDATE sessions SET state=?,ended_at=? WHERE id=?",
                (state, utc() if state == "stopped" else None, ident),
            )
        self.event(ident, "SESSION_" + state.upper(), {})

    def recover(self):
        previous = self.rows(
            "SELECT * FROM sessions WHERE state IN ('recording','paused')"
        )
        with self.transaction() as db:
            db.execute(
                "UPDATE sessions SET state='interrupted' WHERE state IN ('recording','paused')"
            )
        for row in previous:
            self.event(row["id"], "PROCESS_RESTART", {"previous_state": row["state"]})
        return previous

    def device(self, packet):
        with self.transaction() as db:
            db.execute(
                "INSERT INTO devices VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET info_json=excluded.info_json,seen_at=excluded.seen_at",
                (packet["device_id"], json.dumps(packet), utc()),
            )
            db.execute(
                "INSERT OR IGNORE INTO firmware_versions VALUES(?,?)",
                (packet["firmware_version"], json.dumps(packet)),
            )
            if packet.get("model_sha256"):
                db.execute(
                    "INSERT OR IGNORE INTO model_versions VALUES(?,?)",
                    (packet["model_sha256"], json.dumps(packet)),
                )

    def ingest_batch(self, session, frames, recording=True):
        inserted = []
        with self.transaction() as db:
            for raw, packet, error, received_at, epoch in frames:
                db.execute(
                    "INSERT INTO packets(session_id,received_at,received_epoch,raw,error) VALUES(?,?,?,?,?)",
                    (session, received_at, epoch, raw, error),
                )
                if not packet:
                    continue
                if packet["type"] in ("baseline_info", "calibration_complete"):
                    db.execute(
                        "INSERT INTO calibrations(device_id,session_id,created_at,firmware_baseline_id,payload_json) VALUES(?,?,?,?,?)",
                        (
                            packet["device_id"],
                            session,
                            received_at,
                            str(packet.get("baseline_id", "")),
                            json.dumps(packet, allow_nan=False),
                        ),
                    )
                if (
                    packet["type"] != "reading"
                    or not session
                    or not recording
                    or error == "DUPLICATE_OR_OUT_OF_ORDER"
                ):
                    continue
                flags = quality(packet)
                if error and error != "OK":
                    flags = [f for f in flags if f != "VALID"] + [error]
                values = [
                    session,
                    packet["device_id"],
                    packet["boot_id"],
                    packet["sequence"],
                    received_at,
                    epoch,
                    packet["uptime_ms"],
                    "|".join(flags),
                    packet.get("source", "live"),
                    json.dumps(packet, allow_nan=False),
                ] + [packet.get(field) for field in FIELDS]
                columns = (
                    "session_id,device_id,boot_id,sequence,received_at,received_epoch,uptime_ms,quality,source,raw_json,"
                    + ",".join(FIELDS)
                )
                cur = db.execute(
                    f'INSERT OR IGNORE INTO readings({columns}) VALUES({",".join("?" for _ in values)})',
                    values,
                )
                if cur.rowcount:
                    inserted.append(cur.lastrowid)
        return inserted

    def sessions(self):
        return self.rows(
            """SELECT s.*,e.name experiment_name,sa.name sample_name,sa.ground_truth,l.name location_name,l.room,l.material FROM sessions s LEFT JOIN experiments e ON s.experiment_id=e.id LEFT JOIN samples sa ON s.sample_id=sa.id LEFT JOIN locations l ON sa.location_id=l.id ORDER BY s.started_at DESC"""
        )

    def count(self, session):
        return self.rows(
            "SELECT COUNT(*) n FROM readings WHERE session_id=?", (session,)
        )[0]["n"]

    def query(
        self,
        sessions,
        start=None,
        end=None,
        include_flagged=True,
        limit=None,
        offset=0,
        order="received_epoch",
        descending=False,
        search="",
    ):
        if not sessions:
            return []
        if order not in {
            "id",
            "received_at",
            "received_epoch",
            "uptime_ms",
            "quality",
            *FIELDS,
        }:
            raise ValueError("invalid ordering")
        where = "session_id IN (" + ",".join("?" for _ in sessions) + ")"
        args = list(sessions)
        if start is not None:
            where += " AND received_epoch>=?"
            args.append(start)
        if end is not None:
            where += " AND received_epoch<=?"
            args.append(end)
        if not include_flagged:
            where += " AND quality IN ('VALID','WARMING_UP')"
        if search:
            where += " AND (received_at LIKE ? OR quality LIKE ? OR raw_json LIKE ?)"
            args.extend(["%" + search + "%"] * 3)
        sql = (
            f"SELECT * FROM readings WHERE {where} ORDER BY {order} "
            + ("DESC" if descending else "ASC")
            + ",id"
        )
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            args.extend([limit, offset])
        return self.rows(sql, args)

    def iter_readings(self, sessions, start=None, end=None, batch=2000):
        if not sessions:
            return
        last = 0
        maximum = (
            self.rows(
                "SELECT MAX(id) hi FROM readings WHERE session_id IN ("
                + ",".join("?" for _ in sessions)
                + ")",
                sessions,
            )[0]["hi"]
            or 0
        )
        while True:
            sql = (
                "SELECT * FROM readings WHERE session_id IN ("
                + ",".join("?" for _ in sessions)
                + ") AND id>? AND id<=?"
            )
            args = [*sessions, last, maximum]
            if start is not None:
                sql += " AND received_epoch>=?"
                args.append(start)
            if end is not None:
                sql += " AND received_epoch<=?"
                args.append(end)
            data = self.rows(sql + " ORDER BY id LIMIT ?", [*args, batch])
            if not data:
                break
            yield from data
            last = data[-1]["id"]

    def iter_analysis(
        self, sessions, wall_field="wall_cap_filtered", start=None, end=None
    ):
        if not sessions:
            return
        if wall_field not in FIELDS:
            raise ValueError("Unknown analysis signal")
        columns = list(
            dict.fromkeys(
                [
                    "session_id",
                    "boot_id",
                    "quality",
                    "gas_observation_id",
                    "gas_heater_index",
                    wall_field,
                    "gas_resistance_ohms",
                    "temperature_c",
                    "humidity_percent",
                    "mold_probability",
                ]
            )
        )
        sql = (
            "SELECT "
            + ",".join(columns)
            + " FROM readings WHERE session_id IN ("
            + ",".join("?" for _ in sessions)
            + ")"
        )
        args = list(sessions)
        if start is not None:
            sql += " AND received_epoch>=?"
            args.append(start)
        if end is not None:
            sql += " AND received_epoch<=?"
            args.append(end)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            cursor = connection.execute(sql + " ORDER BY session_id,id", args)
            while True:
                batch = cursor.fetchmany(8192)
                if not batch:
                    break
                for row in batch:
                    yield dict(row)
        finally:
            connection.close()

    def plot_rows(self, session, limit=2400, start=None, end=None):
        args = [session]
        where = "session_id=?"
        if start is not None:
            where += " AND received_epoch>=?"
            args.append(start)
        if end is not None:
            where += " AND received_epoch<=?"
            args.append(end)
        bounds = self.rows(
            f"SELECT MIN(received_epoch) lo,MAX(received_epoch) hi,COUNT(*) n FROM readings WHERE {where}",
            args,
        )[0]
        if bounds["n"] <= limit:
            return self.query([session], start, end)
        width = max(0.001, (bounds["hi"] - bounds["lo"]) / max(1, limit // 6))
        # Aggregate six representative IDs per time bucket; saved data is untouched.
        sql = f"""WITH b AS (SELECT id,CAST((received_epoch-?)/? AS INTEGER) bucket,wall_cap_filtered w,gas_resistance_ohms g FROM readings WHERE {where}),
         ranked AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY bucket ORDER BY w,id) wl,ROW_NUMBER() OVER(PARTITION BY bucket ORDER BY w DESC,id) wh,ROW_NUMBER() OVER(PARTITION BY bucket ORDER BY g,id) gl,ROW_NUMBER() OVER(PARTITION BY bucket ORDER BY g DESC,id) gh FROM b),
         chosen AS (SELECT id FROM ranked WHERE wl=1 OR wh=1 OR gl=1 OR gh=1 UNION SELECT MIN(id) FROM b GROUP BY bucket UNION SELECT MAX(id) FROM b GROUP BY bucket)
         SELECT * FROM readings WHERE id IN(SELECT id FROM chosen) ORDER BY received_epoch,id"""
        return self.rows(sql, [bounds["lo"], width, *args])

    def annotate(self, session, text, epoch=None, reading_id=None):
        ident = uid()
        with self.transaction() as db:
            db.execute(
                "INSERT INTO annotations VALUES(?,?,?,?,?,?)",
                (ident, session, utc(), epoch or time.time(), reading_id, text),
            )
        return ident

    def metadata(self, session):
        found = [s for s in self.sessions() if s["id"] == session]
        if not found:
            raise ValueError("Unknown session")
        s = found[0]
        s["parameters"] = json.loads(s["parameters_json"])
        s["analysis_configuration"] = self.rows(
            "SELECT * FROM analysis_configs WHERE id=?", (s["analysis_config_id"],)
        )[0]
        for table in ("annotations", "events", "calibrations"):
            s[table] = self.rows(
                f"SELECT * FROM {table} WHERE session_id=?", (session,)
            )
        return s

    def close(self):
        with self.lock:
            self.db.close()
