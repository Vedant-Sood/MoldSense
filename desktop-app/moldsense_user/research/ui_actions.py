from .ui_common import *


class Actions:
    def refresh_sessions(self):
        sessions = self.db.sessions()
        self.session_map = {
            f"{s['experiment_name']} / {s['name']} · {s['id'][:6]}": s["id"]
            for s in sessions
        }
        values = list(self.session_map)
        self.session_box["values"] = values
        self.control_box["values"] = [""] + values
        self.session_tree.delete(*self.session_tree.get_children())
        for s in sessions:
            self.session_tree.insert(
                "",
                "end",
                iid=s["id"],
                values=[s.get(c, "") for c in self.session_tree["columns"]],
            )
        if self.session:
            for name, ident in self.session_map.items():
                if ident == self.session:
                    self.session_var.set(name)
        elif values:
            self.session_var.set(values[0])
            self.select_session()

    def select_session(self):
        self.session = self.session_map.get(self.session_var.get())
        self.selection = None
        self.selected_summary = None
        self.paused_view = False
        self.table_offset = 0
        self.refresh_plot(force=True)
        self.load_table(0)

    def open_tree_session(self):
        ids = self.session_tree.selection()
        if ids:
            self.session = ids[0]
            for name, ident in self.session_map.items():
                if ident == self.session:
                    self.session_var.set(name)
            self.select_session()
            self.tabs.select(self.views["Live"])

    def new_session(self):
        if self.acq.session and self.acq.recording:
            messagebox.showinfo(
                "Session active", "Stop or pause the current acquisition first."
            )
            return
        dialog = tk.Toplevel(self)
        dialog.title("Experiment and sample")
        dialog.geometry("610x590")
        dialog.transient(self)
        dialog.grab_set()
        entries = {}
        experiments = self.db.rows("SELECT * FROM experiments ORDER BY name")
        locations = self.db.rows("SELECT * FROM locations ORDER BY name")
        for row, (key, label, default) in enumerate(
            [
                ("experiment", "Experiment name", ""),
                ("session", "Session name", ""),
                ("sample", "Sample ID / name", ""),
                ("location", "Location", ""),
                ("room", "Room", ""),
                ("material", "Wall material", ""),
                ("description", "Location description", ""),
                ("label", "Ground truth (blinded = UNKNOWN)", "UNKNOWN"),
                ("notes", "Notes", ""),
            ]
        ):
            ttk.Label(dialog, text=label).grid(
                row=row, column=0, sticky="w", padx=16, pady=10
            )
            var = tk.StringVar(value=default)
            entries[key] = var
            values = (
                LABELS
                if key == "label"
                else (
                    [x["name"] for x in experiments]
                    if key == "experiment"
                    else [x["name"] for x in locations] if key == "location" else None
                )
            )
            widget = (
                ttk.Combobox(dialog, textvariable=var, values=values, width=35)
                if values is not None
                else ttk.Entry(dialog, textvariable=var, width=38)
            )
            widget.grid(row=row, column=1, padx=12, pady=10)

        def save():
            data = {k: v.get().strip() for k, v in entries.items()}
            if not all(
                data[k] for k in ("experiment", "session", "sample", "location")
            ):
                messagebox.showerror(
                    "Required", "Enter experiment, session, sample and location."
                )
                return
            existing = next(
                (e for e in experiments if e["name"] == data["experiment"]), None
            )
            experiment = (
                existing["id"]
                if existing
                else self.db.create_experiment(data["experiment"])
            )
            location = next(
                (e["id"] for e in locations if e["name"] == data["location"]),
                data["location"],
            )
            sample = self.db.create_sample(
                data["sample"],
                location,
                data["room"],
                data["material"],
                data["description"],
                data["label"],
                data["notes"],
            )
            params = {
                **(self.acq.info or {}),
                "baseline": self.acq.baseline,
                "model": self.acq.model,
                "sample_interval_ms": self.acq.latest.get("sample_interval_ms", 1000),
                "location_id": self.db.rows(
                    "SELECT location_id FROM samples WHERE id=?", (sample,)
                )[0]["location_id"],
            }
            self.session = self.db.create_session(
                experiment,
                sample,
                data["session"],
                self.acq.expected_device,
                params,
                self.settings,
            )
            self.db.session_state(self.session, "ready")
            dialog.destroy()
            self.refresh_sessions()
            self.select_session()
            self.status.set(
                "Session ready. Click Start recording after the device connects."
            )

        ttk.Button(dialog, text="Create session", command=save).grid(
            row=10, column=1, pady=15
        )

    def start_recording(self):
        if not self.session:
            messagebox.showinfo("Session", "Create or select a session first.")
            return
        if not self.acq.connected:
            messagebox.showinfo("Device", "Connect a compatible MoldSense first.")
            return
        current = self.db.metadata(self.session)
        if current["state"] == "stopped":
            messagebox.showinfo(
                "Session", "Stopped sessions are immutable. Create a new session."
            )
            return
        if current["device_id"] and current["device_id"] != self.acq.expected_device:
            messagebox.showerror(
                "Device mismatch", "This session belongs to another physical device."
            )
            return
        if self.acq.session and self.acq.session != self.session:
            self.db.session_state(self.acq.session, "paused")
        params = json.loads(current["parameters_json"])
        params.update(
            {
                "device_info": self.acq.info,
                "baseline": self.acq.baseline,
                "model": self.acq.model,
            }
        )
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE sessions SET device_id=?,parameters_json=? WHERE id=?",
                (self.acq.expected_device, json.dumps(params), self.session),
            )
        self.acq.attach_session(self.session, True)
        self.db.session_state(self.session, "recording")
        self.refresh_sessions()
        self.status.set("Recording original packets and readings to SQLite.")

    def pause_recording(self):
        if self.acq.session:
            self.acq.set_recording(False)
            self.db.session_state(self.acq.session, "paused")
            self.refresh_sessions()

    def resume_recording(self):
        self.start_recording()

    def stop_recording(self):
        ident = self.acq.session
        if not ident:
            return
        self.acq.set_recording(False)
        self.db.session_state(ident, "stopped")
        self.acq.attach_session(None, False)
        self.refresh_sessions()
        self.work(
            "auto_summary",
            lambda: session_report(
                self.db,
                ident,
                self.db.root / "reports" / ident / self.safe_stamp(),
                self.settings,
            ),
            lambda p: self.status.set("Session stopped; report: " + str(p)),
        )

    @staticmethod
    def safe_stamp():
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def annotate(self):
        ident = self.acq.session or self.session
        if not ident:
            return
        text = simpledialog.askstring(
            "Annotation",
            "Timestamped observation (separate from ground truth):",
            parent=self,
        )
        if text:
            self.db.annotate(ident, text)
            self.refresh_plot(force=True)

    def load_table(self, offset=None):
        if not self.session:
            return
        if offset is not None:
            self.table_offset = offset
        ident = self.session
        start, end = self.selection or (None, None)
        query = self.search.get()
        order = self.table_order
        desc = self.table_desc
        off = self.table_offset

        def loaded(rows):
            if self.session == ident:
                self.display_table(rows)

        self.work(
            "table",
            lambda: self.db.query(
                [ident], start, end, True, 250, off, order, desc, query
            ),
            loaded,
        )

    def display_table(self, rows):
        self.data_tree.delete(*self.data_tree.get_children())
        for row in rows:
            self.data_tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=[
                    row.get(c, "") if row.get(c) is not None else ""
                    for c in self.data_tree["columns"]
                ],
            )
        self.status.set(
            f"Data page {self.table_offset//250+1}; {len(rows)} original rows displayed."
        )

    def sort_table(self, key):
        self.table_desc = not self.table_desc if self.table_order == key else False
        self.table_order = key
        self.load_table(0)

    def choose_columns(self):
        dialog = tk.Toplevel(self)
        dialog.title("Visible data columns")
        vars = {}
        for i, key in enumerate(self.data_tree["columns"]):
            var = tk.BooleanVar(value=key in self.visible_columns)
            vars[key] = var
            ttk.Checkbutton(dialog, text=key, variable=var).grid(
                row=i // 3, column=i % 3, sticky="w", padx=8, pady=5
            )

        def apply():
            self.visible_columns = [k for k, v in vars.items() if v.get()]
            self.data_tree["displaycolumns"] = self.visible_columns
            dialog.destroy()

        ttk.Button(dialog, text="Apply", command=apply).grid(row=12, column=1, pady=10)

    def jump_time(self):
        value = simpledialog.askstring("Jump", "UTC ISO timestamp:", parent=self)
        if value:
            try:
                epoch = (
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                    .replace(tzinfo=timezone.utc)
                    .timestamp()
                )
                rows = self.db.query([self.session], epoch, limit=1)
            except Exception as e:
                messagebox.showerror("Timestamp", str(e))
                return
            if rows:
                self.show_reading(rows[0])

    def show_reading(self, row):
        self.display_table([row])
        self.data_tree.selection_set(str(row["id"]))
        self.data_tree.see(str(row["id"]))

    def inspect_row(self, event=None):
        ids = self.data_tree.selection()
        if ids:
            row = self.db.rows("SELECT * FROM readings WHERE id=?", (int(ids[0]),))[0]
            dialog = tk.Toplevel(self)
            dialog.title("Original reading " + ids[0])
            dialog.geometry("820x600")
            text = self.text_view(dialog)
            self.write_text(text, json.dumps(row, indent=2))

    def send(self, cmd):
        if not self.acq.connected:
            messagebox.showinfo("Device", "No compatible MoldSense connected.")
            return None
        try:
            return self.acq.send(cmd)
        except Exception as error:
            messagebox.showerror("Command", str(error))
            return None

    def request_guarded(self, cmd):
        descriptions = {
            "START_BASELINE": "Calibrate the wall on a dry reference? BSEC is preserved.",
            "CLEAR_LOG": "Delete only the device CSV log? Desktop data and BSEC remain intact.",
            "NEW_SITE": "Reset exposure history for a new wall position?",
        }
        if messagebox.askyesno("Confirm device action", descriptions[cmd], parent=self):
            request = self.send(cmd)
            if request:
                self.pending[request] = cmd

    def select_port(self):
        from serial.tools import list_ports

        ports = list(list_ports.comports())
        text = "\n".join(f"{p.device}: {p.description}" for p in ports)
        port = simpledialog.askstring(
            "Select device", text + "\n\nPort to verify:", parent=self
        )
        if port:
            if self.acq.recording:
                messagebox.showinfo(
                    "Pause acquisition",
                    "Pause acquisition before changing the selected serial port.",
                )
                return
            self.acq.select_device(port, None)
            self.status.set(
                "Port selected; PING identity verification is still required."
            )

    def dump_log(self):
        if self.acq.recording:
            messagebox.showinfo(
                "Device log", "Pause acquisition before downloading device logs."
            )
            return
        self.send("DUMP_LOG")
        self.status.set(
            "Downloading CRC-checked chunks into device_logs; partial downloads remain marked."
        )

    def change_settings(self):
        self.settings = {
            **self.settings,
            "include_flagged": self.include_flagged.get(),
            "gas_heater_index": int(self.heater.get()),
        }
        config = self.db.analysis_config(self.settings)
        self.write_text(
            self.settings_text,
            json.dumps(self.settings, indent=2)
            + "\nAnalysis version "
            + config
            + "\nOriginal values and historical configurations remain unchanged.",
        )
        self.refresh_plot(force=True)

    def export_graph(self, analysis=False):
        path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("SVG", "*.svg")],
        )
        if path:
            try:
                save_figure(
                    self.analysis_fig if analysis else self.figure,
                    path,
                    (
                        getattr(self, "analysis_metadata", {})
                        if analysis
                        else {
                            "session": self.metadata,
                            "settings": self.settings,
                            "wall_field": self.wall_field.get(),
                            "control_session": self.session_map.get(
                                self.control_var.get()
                            ),
                            "control_means": self.reference,
                            "selected_range": self.selection,
                            "reference_lines": {
                                k: v.get() for k, v in self.line_options.items()
                            },
                        }
                    ),
                )
                self.status.set("Figure exported: " + path)
            except Exception as e:
                messagebox.showerror("Export", str(e))

    def export_data(self, kind, selected=False, ids=None):
        ids = ids or ([self.session] if self.session else [])
        if not ids:
            return
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".json" if kind == "json" else ".csv"
        )
        if path:
            start, end = self.selection if selected and self.selection else (None, None)
            variables = (
                [c for c in self.visible_columns if c in FIELDS] if selected else None
            )
            self.work(
                "export",
                lambda: export_data(self.db, ids, path, kind, start, end, variables),
                lambda p: self.status.set("Exported " + str(p)),
            )

    def export_experiment(self):
        if self.session:
            exp = self.db.metadata(self.session)["experiment_id"]
            ids = [s["id"] for s in self.db.sessions() if s["experiment_id"] == exp]
            self.export_data("json", ids=ids)

    def export_rows(self):
        ids = [int(i) for i in self.data_tree.selection()]
        if not ids:
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".json")
        if path:
            rows = self.db.rows(
                "SELECT * FROM readings WHERE id IN ("
                + ",".join("?" for _ in ids)
                + ")",
                ids,
            )
            Path(path).write_text(
                json.dumps(
                    {"metadata": self.db.metadata(self.session), "readings": rows},
                    indent=2,
                ),
                encoding="utf-8",
            )
            self.status.set("Selected rows exported.")

    def report(self):
        ident = self.session
        if not ident:
            return
        folder = filedialog.askdirectory(parent=self, title="Report output folder")
        if folder:
            settings = {
                **self.settings,
                "wall_field": self.wall_field.get(),
                "control_session_id": self.session_map.get(self.control_var.get()),
            }
            reference = dict(self.reference)
            self.work(
                "report",
                lambda: session_report(
                    self.db,
                    ident,
                    Path(folder) / ("MoldSense_" + self.safe_stamp()),
                    settings,
                    reference,
                ),
                lambda p: self.status.set("Report ready: " + str(p)),
            )

    def import_file(self):
        path = filedialog.askopenfilename(
            parent=self, filetypes=[("Legacy logs", "*.csv *.bmerawdata")]
        )
        if path:
            self.work(
                "import",
                lambda: import_legacy(self.db, path),
                lambda ident: self.import_done(ident),
            )

    def import_archives(self):
        from .migration import import_archives
        from ..storage import Store

        def run():
            store = Store()
            result = import_archives(self.db, store)
            store.db.close()
            return result

        self.work(
            "import_archives",
            run,
            lambda ids: self.import_done(ids[-1] if ids else None),
        )

    def import_done(self, ident):
        self.session = ident or self.session
        self.refresh_sessions()
        self.select_session()
        self.status.set("Legacy data imported; absent measurements remain unavailable.")

    def toggle_presentation(self):
        self.presentation = not self.presentation
        if self.presentation:
            self.controls.pack_forget()
            self.plot_controls.pack_forget()
            self.toolbar.pack_forget()
            self.tabs.select(self.views["Live"])
            for name in self.views:
                if name != "Live":
                    self.tabs.hide(self.views[name])
            self.bind("<Escape>", lambda e: self.toggle_presentation())
            self.status.set(
                "Presentation mode. Esc restores controls. Acquisition continues."
            )
        else:
            self.controls.pack(fill="x", before=self.select_bar)
            self.plot_controls.pack(fill="x", before=self.canvas.get_tk_widget())
            self.toolbar.pack(fill="x")
            for name in self.views:
                self.tabs.add(self.views[name], text=name)

    def tab_changed(self):
        if self.tabs.select() == str(self.views["Data"]):
            self.load_table()
        elif self.tabs.select() == str(self.views["Device"]):
            self.update_health()

    def update_health(self):
        info = {
            "connected": self.acq.connected,
            "port": self.acq.port,
            "identity": self.acq.info,
            "health": self.acq.health,
            "packets_lost": self.acq.tracker.lost,
            "duplicates": self.acq.tracker.duplicates,
            "ui_events_coalesced": self.acq.ui_dropped,
            "latest_reading": self.acq.latest,
        }
        if self.debug_packets.get():
            info["recent_original_frames"] = self.db.rows(
                "SELECT received_at,raw,error FROM packets ORDER BY id DESC LIMIT 25"
            )
        self.write_text(self.device_text, json.dumps(info, indent=2))
