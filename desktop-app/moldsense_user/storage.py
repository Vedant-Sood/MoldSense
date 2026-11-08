import csv, hashlib, json, os, sqlite3
from datetime import datetime, timezone
from pathlib import Path

def data_root():
    override=os.getenv("MOLDSENSE_DATA_DIR")
    return Path(override) if override else Path(os.getenv("LOCALAPPDATA") or Path.home()) / "MoldSense" / "UserDashboard"

class Store:
    def __init__(self, root=None):
        self.root = Path(root) if root else data_root(); self.archives = self.root / "archives"
        self.archives.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "moldsense.db", check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS imports(id INTEGER PRIMARY KEY, imported_at TEXT, port TEXT, remote_name TEXT, local_path TEXT, bytes INTEGER, sha256 TEXT UNIQUE)")
        self.db.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)"); self.db.commit()

    def archive(self, remote_name, payload, port=""):
        digest = hashlib.sha256(payload).hexdigest(); stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        known=self.db.execute("SELECT local_path FROM imports WHERE sha256=?",(digest,)).fetchone()
        if known and Path(known[0]).is_file(): return Path(known[0]), digest
        folder = self.archives / stamp; folder.mkdir(exist_ok=True); path = folder / Path(remote_name).name
        if path.exists(): path = folder / f"{path.stem}_{digest[:8]}{path.suffix}"
        path.write_bytes(payload)
        self.db.execute("INSERT INTO imports(imported_at,port,remote_name,local_path,bytes,sha256) VALUES(?,?,?,?,?,?) ON CONFLICT(sha256) DO UPDATE SET local_path=excluded.local_path", (datetime.now(timezone.utc).isoformat(),port,remote_name,str(path),len(payload),digest)); self.db.commit()
        path.with_suffix(path.suffix+".manifest.json").write_text(json.dumps({"remote_name":remote_name,"saved_path":str(path),"bytes":len(payload),"sha256":digest,"port":port},indent=2),encoding="utf-8")
        return path, digest

    def csv_rows(self):
        rows=[]
        for path in self.archives.rglob("*.csv"):
            rows.extend(self.csv_file_rows(path))
        return rows

    def csv_file_rows(self,path):
        rows=[]; path=Path(path)
        try:
            with path.open(encoding="utf-8-sig",errors="replace",newline="") as handle:
                for row in csv.DictReader(handle):
                    if any(k in row for k in ("iaq","temperature_c","comp_temperature_c")): row["_source"]=str(path); rows.append(row)
        except OSError: pass
        return rows

    def imports(self): return self.db.execute("SELECT imported_at,remote_name,bytes,sha256,local_path FROM imports ORDER BY id DESC").fetchall()
    def set_json(self,key,value):
        self.db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,json.dumps(value))); self.db.commit()
    def get_json(self,key,default=None):
        row=self.db.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone(); return json.loads(row[0]) if row else default
