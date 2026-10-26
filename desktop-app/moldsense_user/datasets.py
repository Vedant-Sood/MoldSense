from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .analysis import METRICS, metric_value
from .references import bundled_capture_rows, bundled_files, capture_rows


@dataclass
class Dataset:
    key: str
    name: str
    kind: str
    rows: list
    path: str = ""
    created: str = "Bundled"
    size: int = 0
    sha256: str = ""
    mode: str = ""

    @property
    def readings(self): return len(self.rows)
    def supports(self,metric): return any(metric_value(row,metric) is not None for row in self.rows)
    def metrics(self): return [key for key in METRICS if self.supports(key)]


def _mode(rows):
    values=sorted({str(row.get("mode","")).strip().upper() for row in rows if str(row.get("mode","")).strip()})
    return ", ".join(values) if values else "Sensor capture"


def build_catalog(store):
    items=[]
    all_rows=store.csv_rows()
    if all_rows:
        items.append(Dataset("all-logs","All saved environmental readings","Saved history",all_rows,created="Local archive",mode=_mode(all_rows)))
    sample_rows=bundled_capture_rows()
    file_info={name:(path,size,sha) for name,path,size,sha in bundled_files()}
    display={"Cap 1":"Cap 1 · Reference capture","Cap 1 Tailored To Cap 2":"Cap 1 · Tailored to Cap 2","Cap 2":"Cap 2 · Reference capture"}
    for index,(name,rows) in enumerate(sample_rows.items()):
        path,size,sha=file_info[name]
        items.append(Dataset(f"bundled-{index}",display.get(name,name),"Bundled reference",rows,str(path),"Bundled",size,sha,"CAPTURE"))
    for index,(created,remote,size,sha,path_text) in enumerate(store.imports()):
        path=Path(path_text)
        if not path.exists(): continue
        try:
            if path.suffix.lower()==".bmerawdata": rows=capture_rows(path)
            elif path.suffix.lower()==".csv": rows=store.csv_file_rows(path)
            else: continue
        except (OSError,ValueError,KeyError): continue
        if not rows: continue
        stamp=created[:16].replace("T"," ")
        items.append(Dataset(f"import-{index}",f"{path.stem.replace('_',' ').title()} · {stamp}","Imported test",rows,str(path),stamp,size,sha,_mode(rows)))
    return items
