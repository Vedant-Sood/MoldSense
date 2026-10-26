"""Layout only; actions, transport and scientific calculations are separate."""

from .ui_common import *


class Layout:
    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10))
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=INK)
        style.configure("TButton", padding=7)
        style.configure("Treeview", rowheight=26, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 9))
        style.configure("TNotebook.Tab", padding=(12, 8))

    def button(self, parent, label, command):
        button = ttk.Button(parent, text=label, command=command)
        button.pack(side="left", padx=3, pady=3)
        return button

    def text_view(self, parent):
        text = tk.Text(
            parent,
            wrap="word",
            bg="white",
            fg=INK,
            relief="flat",
            font=("Consolas", 10),
            padx=16,
            pady=16,
        )
        text.pack(fill="both", expand=True)
        return text

    def write_text(self, widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", text)
        widget.configure(state="disabled")

    def _shell(self):
        top = ttk.Frame(self, padding=(18, 12))
        top.pack(fill="x")
        ttk.Label(top, text="MOLDSENSE", font=("Segoe UI Semibold", 20)).pack(
            side="left"
        )
        ttk.Label(top, text="  RESEARCH WORKSPACE", foreground=MUTED).pack(side="left")
        self.connection = tk.StringVar(value="Searching for MoldSense…")
        ttk.Label(top, textvariable=self.connection).pack(side="right")
        self.controls = ttk.Frame(self, padding=(14, 0))
        self.controls.pack(fill="x")
        for label, action in [
            ("New session", self.new_session),
            ("Start recording", self.start_recording),
            ("Pause acquisition", self.pause_recording),
            ("Resume acquisition", self.resume_recording),
            ("Stop session", self.stop_recording),
            ("Annotate", self.annotate),
            ("Presentation", self.toggle_presentation),
        ]:
            self.button(self.controls, label, action)
        self.select_bar = ttk.Frame(self, padding=(18, 6))
        self.select_bar.pack(fill="x")
        ttk.Label(self.select_bar, text="Session").pack(side="left")
        self.session_var = tk.StringVar()
        self.session_box = ttk.Combobox(
            self.select_bar, textvariable=self.session_var, state="readonly", width=66
        )
        self.session_box.pack(side="left", padx=8)
        self.session_box.bind("<<ComboboxSelected>>", lambda e: self.select_session())
        self.record_state = tk.StringVar(value="NOT RECORDING")
        ttk.Label(
            self.select_bar,
            textvariable=self.record_state,
            font=("Segoe UI Semibold", 10),
        ).pack(side="right")
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=14, pady=6)
        self.views = {}
        for name in (
            "Live",
            "Experiments",
            "Analysis",
            "Data",
            "Calibrations",
            "Device",
            "Reports",
            "Settings",
        ):
            frame = ttk.Frame(self.tabs, padding=10)
            self.tabs.add(frame, text=name)
            self.views[name] = frame
        self._live()
        self._experiments()
        self._analysis()
        self._data()
        self._calibrations()
        self._device()
        self._reports()
        self._settings()
        self.status = tk.StringVar(value="Ready. Raw data stays local.")
        ttk.Label(self, textvariable=self.status, padding=(18, 8)).pack(fill="x")
        self.tabs.bind("<<NotebookTabChanged>>", lambda e: self.tab_changed())

    def _live(self):
        frame = self.views["Live"]
        cards = ttk.Frame(frame)
        cards.pack(fill="x")
        self.wall_card = tk.StringVar(value="WALL RESPONSE\n—")
        self.gas_card = tk.StringVar(value="GAS RESISTANCE\n—")
        for var, color in ((self.wall_card, ACCENT), (self.gas_card, "#365b85")):
            tk.Label(
                cards,
                textvariable=var,
                bg="white",
                fg=color,
                font=("Segoe UI Semibold", 15),
                justify="left",
                anchor="w",
                padx=16,
                pady=12,
            ).pack(side="left", fill="x", expand=True, padx=4)
        self.plot_controls = ttk.Frame(frame)
        self.plot_controls.pack(fill="x", pady=4)
        self.wall_field = tk.StringVar(value="wall_cap_filtered")
        box = ttk.Combobox(
            self.plot_controls,
            textvariable=self.wall_field,
            values=["wall_cap_raw", "wall_cap_filtered", "wall_moisture_index"],
            state="readonly",
            width=23,
        )
        box.pack(side="left", padx=3)
        box.bind("<<ComboboxSelected>>", lambda e: self.refresh_plot(force=True))
        self.window = tk.StringVar(value="15 minutes")
        box = ttk.Combobox(
            self.plot_controls,
            textvariable=self.window,
            values=[
                "1 minute",
                "5 minutes",
                "15 minutes",
                "1 hour",
                "Entire session",
                "Custom",
            ],
            state="readonly",
            width=14,
        )
        box.pack(side="left", padx=3)
        box.bind("<<ComboboxSelected>>", lambda e: self.window_changed())
        for label, action in [
            ("Pause view", lambda: self.set_view_pause(True)),
            ("Resume live", lambda: self.set_view_pause(False)),
            ("Reset zoom", self.reset_zoom),
            ("Select range", self.activate_range),
            ("Export figure", self.export_graph),
        ]:
            self.button(self.plot_controls, label, action)
        lines = ttk.Frame(frame)
        lines.pack(fill="x")
        self.line_options = {}
        for key, label in [
            ("session", "Session mean"),
            ("rolling", "Rolling mean"),
            ("selected", "Range mean"),
            ("control", "Control mean"),
            ("baseline", "Baseline"),
            ("warning", "Wall alert"),
        ]:
            var = tk.BooleanVar(value=key != "warning")
            self.line_options[key] = var
            ttk.Checkbutton(
                lines, text=label, variable=var, command=lambda: self.render_current()
            ).pack(side="left", padx=4)
        self.figure = Figure(figsize=(11, 5), dpi=100, layout="constrained")
        self.canvas = FigureCanvasTkAgg(self.figure, master=frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.toolbar = NavigationToolbar2Tk(self.canvas, frame, pack_toolbar=False)
        self.toolbar.pack(fill="x")
        self.canvas.mpl_connect("motion_notify_event", self.hover)
        self.canvas.mpl_connect("button_press_event", self.click_point)
        self.evidence = tk.StringVar(
            value="No device readings. The index is an unvalidated screening score."
        )
        ttk.Label(frame, textvariable=self.evidence, wraplength=1250).pack(
            fill="x", pady=4
        )

    def _experiments(self):
        frame = self.views["Experiments"]
        bar = ttk.Frame(frame)
        bar.pack(fill="x")
        for label, fn in [
            ("Refresh", self.refresh_sessions),
            ("New experiment / sample", self.new_session),
            ("Import legacy file", self.import_file),
            ("Import archived legacy files", self.import_archives),
        ]:
            self.button(bar, label, fn)
        columns = (
            "experiment_name",
            "name",
            "sample_name",
            "location_name",
            "ground_truth",
            "state",
            "started_at",
        )
        self.session_tree = ttk.Treeview(
            frame, columns=columns, show="headings", selectmode="extended"
        )
        for c in columns:
            self.session_tree.heading(c, text=c.replace("_", " ").title())
            self.session_tree.column(c, width=150)
        self.session_tree.pack(fill="both", expand=True, pady=8)
        self.session_tree.bind("<Double-1>", lambda e: self.open_tree_session())
        ttk.Label(
            frame,
            text="Select multiple sessions for group comparisons. Ground truth remains separate from predictions.",
        ).pack(anchor="w")

    def _analysis(self):
        frame = self.views["Analysis"]
        bar = ttk.Frame(frame)
        bar.pack(fill="x")
        self.analysis_kind = tk.StringVar(value="scatter")
        ttk.Combobox(
            bar,
            textvariable=self.analysis_kind,
            values=["scatter", "normalized", "histogram", "box", "longitudinal"],
            state="readonly",
            width=14,
        ).pack(side="left")
        ttk.Label(bar, text="  Control").pack(side="left")
        self.control_var = tk.StringVar()
        self.control_box = ttk.Combobox(
            bar, textvariable=self.control_var, state="readonly", width=35
        )
        self.control_box.pack(side="left", padx=6)
        self.include_flagged = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            bar,
            text="Include flagged",
            variable=self.include_flagged,
            command=self.change_settings,
        ).pack(side="left")
        ttk.Label(bar, text=" Gas heater").pack(side="left")
        self.heater = tk.StringVar(value="0")
        box = ttk.Combobox(
            bar,
            textvariable=self.heater,
            values=[str(i) for i in range(10)],
            width=3,
            state="readonly",
        )
        box.pack(side="left")
        box.bind("<<ComboboxSelected>>", lambda e: self.change_settings())
        self.button(bar, "Analyze selection", self.run_analysis)
        self.button(bar, "Export graph", lambda: self.export_graph(True))
        split = ttk.Panedwindow(frame, orient="vertical")
        split.pack(fill="both", expand=True, pady=8)
        chart = ttk.Frame(split)
        stats = ttk.Frame(split)
        split.add(chart, weight=3)
        split.add(stats, weight=2)
        self.analysis_fig = Figure(figsize=(11, 4), dpi=100, layout="constrained")
        self.analysis_canvas = FigureCanvasTkAgg(self.analysis_fig, master=chart)
        self.analysis_canvas.get_tk_widget().pack(fill="both", expand=True)
        NavigationToolbar2Tk(self.analysis_canvas, chart)
        self.stats_text = self.text_view(stats)

    def _data(self):
        frame = self.views["Data"]
        bar = ttk.Frame(frame)
        bar.pack(fill="x")
        self.search = tk.StringVar()
        ttk.Entry(bar, textvariable=self.search, width=25).pack(side="left")
        for label, action in [
            ("Search", lambda: self.load_table(0)),
            ("Previous", lambda: self.load_table(max(0, self.table_offset - 250))),
            ("Next", lambda: self.load_table(self.table_offset + 250)),
            ("Columns", self.choose_columns),
            ("Jump to UTC", self.jump_time),
            ("Export range", lambda: self.export_data("raw", True)),
            ("Export rows", self.export_rows),
        ]:
            self.button(bar, label, action)
        cols = ["id", "received_at", "uptime_ms", *FIELDS, "quality"]
        self.data_tree = ttk.Treeview(
            frame, columns=cols, show="headings", selectmode="extended"
        )
        self.visible_columns = [
            "id",
            "received_at",
            "wall_cap_raw",
            "wall_cap_filtered",
            "wall_moisture_index",
            "gas_resistance_ohms",
            "gas_rolling_mean",
            "humidity_percent",
            "temperature_c",
            "quality",
        ]
        self.data_tree["displaycolumns"] = self.visible_columns
        for c in cols:
            self.data_tree.heading(
                c, text=c, command=lambda key=c: self.sort_table(key)
            )
            self.data_tree.column(c, width=130, minwidth=75, stretch=False)
        ys = ttk.Scrollbar(frame, orient="vertical", command=self.data_tree.yview)
        xs = ttk.Scrollbar(frame, orient="horizontal", command=self.data_tree.xview)
        self.data_tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        ys.pack(side="right", fill="y")
        xs.pack(side="bottom", fill="x")
        self.data_tree.pack(fill="both", expand=True)
        self.data_tree.bind("<Double-1>", self.inspect_row)

    def _calibrations(self):
        frame = self.views["Calibrations"]
        bar = ttk.Frame(frame)
        bar.pack(fill="x")
        self.button(
            bar, "Calibrate wall", lambda: self.request_guarded("START_BASELINE")
        )
        self.button(bar, "Cancel calibration", lambda: self.send("STOP_BASELINE"))
        self.button(bar, "Read baseline", lambda: self.send("GET_BASELINE"))
        ttk.Label(
            frame,
            text="Hold on a dry reference. Wall calibration never resets BSEC learning or the AI model.",
            padding=10,
        ).pack(anchor="w")
        self.cal_progress = ttk.Progressbar(frame, maximum=100)
        self.cal_progress.pack(fill="x", pady=8)
        self.cal_text = self.text_view(frame)

    def _device(self):
        frame = self.views["Device"]
        bar = ttk.Frame(frame)
        bar.pack(fill="x")
        for label, action in [
            ("Refresh health", lambda: self.send("STATUS")),
            ("Device info", lambda: self.send("DEVICE_INFO")),
            ("Model info", lambda: self.send("MODEL_INFO")),
            ("New wall position", lambda: self.request_guarded("NEW_SITE")),
            ("Select port", self.select_port),
            ("Download log", self.dump_log),
            ("Clear log", lambda: self.request_guarded("CLEAR_LOG")),
        ]:
            self.button(bar, label, action)
        self.debug_packets = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame,
            text="Debug: show recent original protocol frames",
            variable=self.debug_packets,
            command=self.update_health,
        ).pack(anchor="w")
        self.device_text = self.text_view(frame)

    def _reports(self):
        frame = self.views["Reports"]
        ttk.Label(
            frame, text="Reproducible exports", font=("Segoe UI Semibold", 20)
        ).pack(anchor="w", pady=12)
        for label, cmd in [
            ("Raw CSV", lambda: self.export_data("raw")),
            ("Processed CSV", lambda: self.export_data("processed")),
            ("Complete session JSON", lambda: self.export_data("json")),
            ("Complete experiment JSON", self.export_experiment),
            ("Generate session report", self.report),
        ]:
            ttk.Button(frame, text=label, command=cmd).pack(anchor="w", pady=5)
        ttk.Label(
            frame,
            text="Exports preserve source values with device, firmware, model, calibration and analysis metadata.\nReports include standalone PNG/SVG figures. Pausing the view never pauses acquisition.",
            wraplength=1000,
            padding=12,
        ).pack(anchor="w")

    def _settings(self):
        frame = self.views["Settings"]
        bar = ttk.Frame(frame)
        bar.pack(fill="x")
        ttk.Label(bar, text="Telemetry interval (1000–60000 ms)").pack(side="left")
        self.interval = tk.StringVar(value="1000")
        ttk.Entry(bar, textvariable=self.interval, width=8).pack(side="left", padx=8)
        self.button(
            bar,
            "Apply to device",
            lambda: self.send("SET_SAMPLE_INTERVAL " + self.interval.get()),
        )
        self.button(bar, "Save analysis version", self.change_settings)
        self.settings_text = self.text_view(frame)
        self.write_text(
            self.settings_text,
            json.dumps(self.settings, indent=2)
            + "\n\nBSEC controls heater scheduling. Telemetry interval controls snapshots.\nLegacy dashboard: --legacy. No Startup registration.\nDatabase: "
            + str(self.db.path),
        )
