"""Own-application UI QA only; no serial devices opened. All data is SYNTHETIC."""

import json, math, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from moldsense_user.research.database import Database, utc
from moldsense_user.research.protocol import parse_line
from moldsense_user.research.acquisition import Acquisition
from moldsense_user.research.statistics import DEFAULT_SETTINGS
from moldsense_user.research.ui import ResearchApp
from moldsense_user.research.exports import session_report
from test_research import packet

qa = Path(__file__).resolve().parents[2] / "outputs/moldsense_research_qa"
qa.mkdir(parents=True, exist_ok=True)
db = Database(qa / "data")
experiment = db.create_experiment("SYNTHETIC SOFTWARE TEST — not experimental evidence")
sessions = []
for label in ("CONTROL", "DAMP"):
    sample = db.create_sample(
        "SYNTHETIC " + label,
        "Synthetic test wall",
        material="Synthetic gypsum",
        label=label,
    )
    session = db.create_session(
        experiment,
        sample,
        "SYNTHETIC " + label,
        "MOLDSENSE_TEST",
        {"sample_interval_ms": 1000, "synthetic": True},
        DEFAULT_SETTINGS,
        "synthetic",
    )
    sessions.append(session)
    acq = Acquisition(db)
    acq.attach_session(session)
    for i in range(300):
        wall = (
            100
            + math.sin(i / 16) * 0.4
            - (min(24, (i - 100) * 0.15) if label == "DAMP" and i > 100 else 0)
        )
        gas = (
            410000
            + math.sin(i / 20) * 8000
            - (max(0, i - 80) * 190 if label == "DAMP" else 0)
        )
        p = packet(
            i,
            wall_cap_raw=wall,
            wall_cap_filtered=wall,
            wall_moisture_index=max(0, (100 - wall - 3) / 27 * 100),
            wall_deviation=wall - 100,
            gas_resistance_ohms=gas,
            source="synthetic",
            mold_probability=25 if label == "DAMP" else 0,
            risk_level="ELEVATED" if label == "DAMP" else "LOW",
            wall_contribution=22,
            environment_contribution=3,
            condensation_contribution=0,
            voc_contribution=0,
        )
        acq.process(parse_line(json.dumps(p)), 1700000000 + i + (20 if i > 200 else 0))
    db.annotate(session, "SYNTHETIC probe placement annotation", 1700000100)
    db.session_state(session, "stopped")
session_report(db, sessions[1], qa / "sample_report")
db.close()
app = ResearchApp(qa / "data", autoconnect=False)
app.geometry("1400x920+10+10")
app.session = sessions[1]
app.refresh_sessions()
app.select_session()


def pump(seconds=2):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        app.update()
        time.sleep(0.03)


pump(3)
assert app.current_rows and len(app.axes) == 2, app.status.get()
app.update()
box = (
    app.winfo_rootx(),
    app.winfo_rooty(),
    app.winfo_rootx() + app.winfo_width(),
    app.winfo_rooty() + app.winfo_height(),
)
app.figure.savefig(qa / "live_chart.png", dpi=150)
for name in app.views:
    app.tabs.select(app.views[name])
    pump(0.1)
app.session_tree.selection_set(sessions)
app.analysis_kind.set("scatter")
app.tabs.select(app.views["Analysis"])
app.run_analysis()
pump(2)
assert "total_rows" in app.stats_text.get("1.0", "end"), app.status.get()
app.analysis_fig.savefig(qa / "analysis_chart.png", dpi=150)
for kind in ("normalized", "histogram", "box", "longitudinal"):
    app.analysis_kind.set(kind)
    app.run_analysis()
    pump(1)
    assert not any("failed" in app.status.get() for _ in [0]), app.status.get()
app.toggle_presentation()
pump(0.2)
assert app.presentation
app.toggle_presentation()
pump(0.2)
app.set_view_pause(True)
assert app.paused_view and not app.acq.recording
app.load_table(0)
pump(0.5)
assert len(app.data_tree.get_children()) == 250
app.close()
print(
    "PASS UI: 8 tabs, live plots, group analysis, presentation, pause-view, table pagination; synthetic report exported."
)
print(qa)
