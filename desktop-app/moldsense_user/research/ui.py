"""Integrated research workspace in the existing Tkinter framework."""

from .ui_common import *
from .ui_layout import Layout
from .ui_actions import Actions
from .ui_charts import Charts


class ResearchApp(Layout, Actions, Charts, tk.Tk):
    def __init__(self, root=None, autoconnect=True):
        super().__init__()
        self.title("MoldSense · Research instrument")
        self.geometry("1420x940")
        self.minsize(1120, 780)
        self.configure(bg=BG)
        self.db = Database(root)
        self.recovered = self.db.recover()
        self.acq = Acquisition(self.db)
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.jobs = queue.Queue()
        self.busy = set()
        self.session = None
        self.current_rows = []
        self.summary = {}
        self.selected_summary = None
        self.reference = {}
        self.metadata = {}
        self.selection = None
        self.paused_view = False
        self.presentation = False
        self.last_refresh = 0
        self.table_offset = 0
        self.table_order = "received_epoch"
        self.table_desc = False
        self.session_map = {}
        self.pending = {}
        self.settings = dict(DEFAULT_SETTINGS)
        self.closed = False
        self._style()
        self._shell()
        self.refresh_sessions()
        self.protocol("WM_DELETE_WINDOW", self.close)
        if autoconnect:
            self.acq.start()
        self.after(150, self.poll)
        if self.recovered:
            self.status.set(
                f"{len(self.recovered)} interrupted session(s) preserved. Select one and Resume acquisition."
            )

    def work(self, key, fn, done):
        if key in self.busy:
            return
        self.busy.add(key)

        def run():
            try:
                self.jobs.put((key, done, fn(), None))
            except Exception as e:
                self.jobs.put((key, done, None, e))

        self.pool.submit(run)

    def poll(self):
        if self.closed:
            return
        for _ in range(100):
            try:
                key, done, result, error = self.jobs.get_nowait()
            except queue.Empty:
                break
            self.busy.discard(key)
            if error:
                self.status.set(key + " failed: " + str(error))
            else:
                try:
                    done(result)
                except Exception as error:
                    self.status.set(key + " rendering failed: " + str(error))
        for _ in range(100):
            try:
                kind, payload = self.acq.events.get_nowait()
            except queue.Empty:
                break
            if kind == "connected":
                self.connection.set(
                    f"Connected · {payload['port']} · FW {payload['firmware_version']} · Protocol 1"
                )
            elif kind == "disconnected":
                self.connection.set("Disconnected · preserving session · reconnecting")
                self.status.set(str(payload))
            elif kind == "devices":
                options = "\n".join(f"{p['port']} {p['device_id']}" for p in payload)
                port = simpledialog.askstring(
                    "Multiple MoldSense devices",
                    options + "\nSelect port:",
                    parent=self,
                )
                chosen = next((p for p in payload if p["port"] == port), None)
                if chosen:
                    self.acq.select_device(chosen["port"], chosen["device_id"])
            elif kind in (
                "calibration_progress",
                "baseline_info",
                "calibration_complete",
            ):
                self.cal_progress["value"] = payload.get(
                    "progress",
                    (
                        100
                        if kind == "calibration_complete" and payload.get("success")
                        else 0
                    ),
                )
                self.write_text(self.cal_text, json.dumps(payload, indent=2))
            elif kind in ("warning", "error", "protocol_error"):
                self.status.set(
                    kind.upper() + ": " + str(payload.get("reason", payload))
                )
            elif kind == "log_complete":
                self.status.set(
                    "Verified device log: " + str(payload.get("desktop_file"))
                )
            elif kind == "command_ack":
                req = payload.get("request_id")
                command = self.pending.pop(req, None)
                if (
                    command
                    and payload.get("success")
                    and payload.get("confirmation_token")
                ):
                    self.send("CONFIRM " + payload["confirmation_token"])
                self.status.set(
                    f"{payload.get('command')}: {'ACK' if payload.get('success') else 'ERROR'} — {payload.get('reason')}"
                )
            elif kind == "command_timeout":
                self.pending.pop(payload.get("request_id"), None)
                self.status.set(
                    "Command timed out; no blind retry: " + str(payload.get("command"))
                )
        state = (
            "RECORDING"
            if self.acq.recording
            else "PAUSED" if self.acq.session else "NOT RECORDING"
        )
        count = (
            self.acq.stored_count
            if self.acq.session
            else self.summary.get("total_rows", 0)
        )
        seconds = int(
            max(0, time.monotonic() - (self.acq.record_started or time.monotonic()))
        )
        if not self.acq.recording:
            seconds = int(self.acq.record_elapsed)
        elapsed = f"{seconds//3600:02d}:{seconds//60%60:02d}:{seconds%60:02d}"
        self.record_state.set(
            f"{state}  ·  {elapsed} current run  ·  {count:,} readings"
        )
        now = time.monotonic()
        if now - self.last_refresh >= 5:
            self.last_refresh = now
            self.refresh_plot()
            self.update_health()
        self.after(200, self.poll)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.acq.close()
        self.pool.shutdown(wait=True, cancel_futures=True)
        if self.acq.session:
            self.db.session_state(self.acq.session, "interrupted")
        self.db.close()
        self.destroy()


def main():
    ResearchApp().mainloop()
