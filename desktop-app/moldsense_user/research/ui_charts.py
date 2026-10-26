from .ui_common import *


class Charts:
    def set_view_pause(self, value):
        self.paused_view = value
        self.status.set(
            "Visualization paused; acquisition continues."
            if value
            else "Live view resumed."
        )
        self.refresh_plot(force=not value)

    def reset_zoom(self):
        self.selection = None
        self.selected_summary = None
        self.paused_view = False
        self.refresh_plot(force=True)

    def window_changed(self):
        if self.window.get() == "Custom":
            value = simpledialog.askstring(
                "Custom UTC range",
                "Two ISO UTC times separated by a comma:",
                parent=self,
            )
            if value:
                try:
                    self.selection = tuple(
                        datetime.fromisoformat(x.strip().replace("Z", "+00:00"))
                        .replace(tzinfo=timezone.utc)
                        .timestamp()
                        for x in value.split(",")
                    )
                    assert (
                        len(self.selection) == 2
                        and self.selection[0] < self.selection[1]
                    )
                except Exception:
                    messagebox.showerror("Range", "Invalid range")
                    self.selection = None
        self.refresh_plot(force=True)

    def time_range(self):
        if self.window.get() == "Custom" and self.selection:
            return self.selection
        seconds = {
            "1 minute": 60,
            "5 minutes": 300,
            "15 minutes": 900,
            "1 hour": 3600,
        }.get(self.window.get())
        if seconds and self.session:
            end = self.db.rows(
                "SELECT MAX(received_epoch) t FROM readings WHERE session_id=?",
                (self.session,),
            )[0]["t"]
            return (end - seconds, end) if end else (None, None)
        return None, None

    def refresh_plot(self, force=False):
        if not self.session or (self.paused_view and not force):
            return
        ident = self.session
        start, end = self.time_range()
        field = self.wall_field.get()
        settings = dict(self.settings)
        control = self.session_map.get(self.control_var.get())
        selection = self.selection

        def load():
            summary = analyze_database(self.db, [ident], field, settings=settings)
            reference = {}
            if control:
                ref = analyze_database(self.db, [control], field, settings=settings)
                reference = {k: ref[k]["mean"] for k in ("wall", "gas")}
            selected = (
                analyze_database(
                    self.db, [ident], field, reference, settings, *selection
                )
                if selection
                else None
            )
            rows = self.db.plot_rows(ident, start=start, end=end)
            return ident, rows, self.db.metadata(ident), summary, reference, selected

        def loaded(data):
            ident, rows, meta, summary, reference, selected = data
            if self.session != ident:
                return
            self.current_rows = rows
            self.metadata = meta
            self.summary = summary
            self.reference = reference
            self.selected_summary = selected
            self.render_current()

        self.work("live_plot", load, loaded)

    def render_current(self):
        if not self.metadata:
            return
        _, self.axes = time_figure(
            self.current_rows,
            self.metadata,
            self.summary,
            self.wall_field.get(),
            {k: v.get() for k, v in self.line_options.items()},
            self.reference,
            self.selected_summary,
            self.figure,
        )
        self.spans = [
            SpanSelector(
                ax,
                self.on_range,
                "horizontal",
                useblit=False,
                props={"alpha": 0.15, "facecolor": ACCENT},
                interactive=True,
            )
            for ax in self.axes
        ]
        for span in self.spans:
            span.set_active(False)
        self.canvas.draw_idle()
        self.update_cards()

    def activate_range(self):
        self.paused_view = True
        for span in getattr(self, "spans", []):
            span.set_active(True)
        self.status.set("Drag a range. Rendering pauses; acquisition continues.")

    def on_range(self, left, right):
        self.selection = (
            mdates.num2date(left).timestamp(),
            mdates.num2date(right).timestamp(),
        )
        self.paused_view = True
        self.refresh_plot(force=True)
        self.status.set("Selected range stored for statistics and export.")

    def hover(self, event):
        if event.xdata is None or not self.current_rows:
            return
        epoch = mdates.num2date(event.xdata).timestamp()
        row = min(self.current_rows, key=lambda r: abs(r["received_epoch"] - epoch))
        base = row.get("wall_baseline")
        value = row.get("wall_cap_filtered")
        mean = self.summary.get("wall", {}).get("mean")
        self.status.set(
            f"{row['received_at']} | uptime {row['uptime_ms']} ms | raw {fmt(row.get('wall_cap_raw'))} filtered {fmt(value)} mean {fmt(mean)} baseline {fmt(base)} Δ {fmt(value-base if value is not None and base is not None else None)} ({fmt(percent(value,base))}%) | gas {fmt(row.get('gas_resistance_ohms'))} Ω | ID {row['id']}"
        )

    def click_point(self, event):
        if event.xdata is None or not self.current_rows:
            return
        self.paused_view = True
        epoch = mdates.num2date(event.xdata).timestamp()
        row = min(self.current_rows, key=lambda r: abs(r["received_epoch"] - epoch))
        self.status.set(
            f"Selected reading {row['id']}. Double-click to open raw table."
        )
        if event.dblclick:
            self.tabs.select(self.views["Data"])
            self.show_reading(row)

    def update_cards(self):
        row = self.current_rows[-1] if self.current_rows else {}
        field = self.wall_field.get()
        value = row.get(field)
        baseline = (
            0
            if field == "wall_moisture_index" and row.get("wall_baseline") is not None
            else row.get("wall_baseline")
        )
        mean = self.summary.get("wall", {}).get("mean")
        self.wall_card.set(
            f"WALL RESPONSE    {fmt(value)}\nBaseline {fmt(baseline)}   Δ {fmt(value-baseline if value is not None and baseline is not None else None)} ({fmt(percent(value,baseline))}%)\nSession mean {fmt(mean)}   Δ mean {fmt(value-mean if value is not None and mean is not None else None)}"
        )
        gas_row = next(
            (
                r
                for r in reversed(self.current_rows)
                if r.get("gas_heater_index")
                in (None, self.settings["gas_heater_index"])
            ),
            {},
        )
        gas = gas_row.get("gas_resistance_ohms")
        gm = self.summary.get("gas", {}).get("mean")
        scale, unit = gas_unit([gas, gm])
        self.gas_card.set(
            f'GAS RESISTANCE · STEP {self.settings["gas_heater_index"]}    {fmt(gas/scale if gas is not None else None)} {unit}\nSession mean {fmt(gm/scale if gm is not None else None)} {unit}   Δ {fmt((gas-gm)/scale if gas is not None and gm is not None else None)}\nDeviation {fmt(percent(gas,gm))}%   Control {fmt(self.reference.get("gas")/scale if self.reference.get("gas") is not None else None)} {unit}'
        )
        packet = (
            self.acq.latest
            if self.acq.session == self.session and self.acq.recording
            else json.loads(row.get("raw_json", "{}"))
        )
        self.evidence.set(
            "Screening index "
            + fmt(packet.get("mold_probability"))
            + "% | Confidence "
            + fmt(packet.get("confidence"))
            + "% | "
            + str(packet.get("risk_level", "UNKNOWN"))
            + " | RH "
            + fmt(packet.get("humidity_percent"))
            + "% | Contributions: wall +"
            + fmt(packet.get("wall_contribution"))
            + ", environment +"
            + fmt(packet.get("environment_contribution"))
            + ", condensation +"
            + fmt(packet.get("condensation_contribution"))
            + ", VOC +"
            + fmt(packet.get("voc_contribution"))
            + ". Unvalidated score; gas resistance alone does not identify mold."
        )

    def selected_sessions(self):
        return list(self.session_tree.selection()) or (
            [self.session] if self.session else []
        )

    def run_analysis(self):
        ids = self.selected_sessions()
        kind = self.analysis_kind.get()
        field = self.wall_field.get()
        settings = dict(self.settings)
        control = self.session_map.get(self.control_var.get())
        selection = self.selection
        if not ids:
            return

        def run():
            groups = {}
            summaries = {}
            reference = {}
            distributions = {}
            records = {}
            if control:
                ref = analyze_database(self.db, [control], field, settings=settings)
                reference = {k: ref[k]["mean"] for k in ("wall", "gas")}
            for ident in ids:
                meta = self.db.metadata(ident)
                label = f"{meta['ground_truth']} · {meta['name']} · {ident[:5]}"
                records[label] = meta
                groups[label] = self.db.plot_rows(
                    ident,
                    start=selection[0] if selection else None,
                    end=selection[1] if selection else None,
                )
                summaries[label] = analyze_database(
                    self.db,
                    [ident],
                    field,
                    reference,
                    settings,
                    *(selection or (None, None)),
                )
                if kind in ("histogram", "box"):
                    distributions[label] = distributions_database(
                        self.db, [ident], field, settings, *(selection or (None, None))
                    )
            return groups, summaries, reference, distributions, records

        def show(result):
            groups, summaries, reference, distributions, records = result
            if kind == "longitudinal":
                longitudinal_figure(records, summaries, self.analysis_fig)
            elif kind in ("histogram", "box"):
                distribution_figure(distributions, kind, field, self.analysis_fig)
            else:
                analysis_figure(
                    groups,
                    kind,
                    field,
                    settings["gas_heater_index"],
                    settings["include_flagged"],
                    self.analysis_fig,
                    reference,
                    summaries,
                )
            self.analysis_canvas.draw_idle()
            self.write_text(
                self.stats_text,
                json.dumps(
                    {"control_means": reference, "sessions": summaries},
                    indent=2,
                    ensure_ascii=False,
                ),
            )
            self.analysis_metadata = {
                "sessions": [self.db.metadata(i) for i in ids],
                "settings": settings,
                "statistics": summaries,
            }
            self.status.set(
                "Analysis complete. Full-data statistics; plotted points may be reduced."
            )

        self.work("analysis", run, show)
