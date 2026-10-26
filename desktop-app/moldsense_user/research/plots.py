"""Scientific figures; decimation affects rendering only."""

from datetime import datetime, timezone
import math
import numpy as np
from matplotlib.figure import Figure
from matplotlib import dates as mdates
from .statistics import percent, valid_row, pair_values

WALL = "#176b62"
GAS = "#365b85"
REFERENCE = "#936623"
MEAN = "#786183"


def gas_unit(values):
    scale = max(
        [abs(v) for v in values if v is not None and math.isfinite(v)], default=0
    )
    return (1e6, "MΩ") if scale >= 1e6 else (1000, "kΩ") if scale >= 1000 else (1, "Ω")


def timeline(rows, field, scale=1, interval=1, events=()):
    x = []
    y = []
    previous = None
    boundaries = sorted(
        e["epoch"]
        for e in events
        if e.get("kind")
        in (
            "DISCONNECTED",
            "CONNECTED",
            "SESSION_PAUSED",
            "SESSION_RECORDING",
            "PROCESS_RESTART",
        )
    )
    for row in rows:
        epoch = row["received_epoch"]
        date = mdates.date2num(datetime.fromtimestamp(epoch, timezone.utc))
        if previous is not None and (
            row["boot_id"] != previous["boot_id"]
            or epoch - previous["received_epoch"]
            > max(3, interval * max(1, row.get("id", 0) - previous.get("id", 0)) * 1.5)
            or any(previous["received_epoch"] < b <= epoch for b in boundaries)
        ):
            x.append(date)
            y.append(float("nan"))
        x.append(date)
        value = row.get(field)
        y.append(
            value / scale
            if value is not None and math.isfinite(value)
            else float("nan")
        )
        previous = row
    return x, y


def style_axis(ax, ylabel):
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.16)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=8)


def time_figure(
    rows,
    metadata,
    summary,
    wall_field="wall_cap_filtered",
    toggles=None,
    reference=None,
    selected=None,
    figure=None,
):
    toggles = toggles or {
        "session": True,
        "rolling": True,
        "baseline": True,
        "control": True,
        "selected": True,
        "warning": False,
    }
    reference = reference or {}
    fig = figure or Figure(figsize=(11, 6), dpi=110, layout="constrained")
    fig.clear()
    axes = fig.subplots(2, 1, sharex=True)
    title = metadata.get("sample_name") or metadata.get("name", "MoldSense")
    fig.suptitle(
        title + " · wall response and gas resistance", fontsize=12, weight="bold"
    )
    scale, unit = gas_unit([r.get("gas_resistance_ohms") for r in rows])
    interval = metadata.get("parameters", {}).get("sample_interval_ms", 1000) / 1000
    events = metadata.get("events", [])
    for ax, field, color, label, div, key in (
        (
            axes[0],
            wall_field,
            WALL,
            (
                "Wall Moisture Index (relative 0–100)"
                if wall_field == "wall_moisture_index"
                else "Wall response (touch/ADC units)"
            ),
            1,
            "wall",
        ),
        (
            axes[1],
            "gas_resistance_ohms",
            GAS,
            "Gas resistance (" + unit + ")",
            scale,
            "gas",
        ),
    ):
        plot_rows = (
            [
                r
                for r in rows
                if r.get("gas_heater_index")
                in (None, summary.get("gas_heater_index", 0))
            ]
            if key == "gas"
            else rows
        )
        if key == "gas":
            label += " · heater step " + str(summary.get("gas_heater_index", 0))
        x, y = timeline(plot_rows, field, div, interval, events)
        ax.plot(x, y, color=color, lw=1.2, label="Measured signal")
        mean = summary.get(key, {}).get("mean")
        if toggles.get("session") and mean is not None:
            ax.axhline(mean / div, color=MEAN, ls="--", lw=1, label="Session mean")
        if toggles.get("rolling"):
            rx, ry = timeline(
                plot_rows,
                (
                    "gas_rolling_mean"
                    if key == "gas"
                    else {
                        "wall_cap_raw": "wall_raw_rolling_mean",
                        "wall_cap_filtered": "wall_rolling_mean",
                        "wall_moisture_index": "wall_index_rolling_mean",
                    }[field]
                ),
                div,
                interval,
                events,
            )
            if any(math.isfinite(v) for v in ry):
                ax.plot(
                    rx,
                    ry,
                    color=color,
                    ls=":",
                    lw=1.5,
                    label="Rolling mean (30 observations)",
                )
        if key == "wall" and toggles.get("baseline"):
            baseline_rows = [
                {
                    **r,
                    "_baseline": (
                        0
                        if field == "wall_moisture_index"
                        and r.get("wall_baseline") is not None
                        else r.get("wall_baseline")
                    ),
                }
                for r in rows
            ]
            bx, by = timeline(baseline_rows, "_baseline", events=events)
            ax.plot(bx, by, color=REFERENCE, ls="-.", lw=1.3, label="Dry-wall baseline")
        if toggles.get("control") and reference.get(key) is not None:
            ax.axhline(
                reference[key] / div,
                color=REFERENCE,
                ls=":",
                lw=1.5,
                label="Control mean",
            )
        if (
            toggles.get("selected")
            and selected
            and selected.get(key, {}).get("mean") is not None
        ):
            ax.axhline(
                selected[key]["mean"] / div,
                color="#ad6559",
                ls="--",
                label="Selected-range mean",
            )
        if toggles.get("warning") and key == "wall" and field == "wall_moisture_index":
            parameters = metadata.get("parameters", {})
            alert = parameters.get("device_info", parameters).get("wall_abnormal")
            if isinstance(alert, (int, float)) and math.isfinite(alert):
                ax.axhline(
                    alert,
                    color="#b66b25",
                    ls=":",
                    label=f"Configured relative alert ({alert:g})",
                )
        for note in metadata.get("annotations", []):
            date = mdates.date2num(datetime.fromtimestamp(note["epoch"], timezone.utc))
            ax.axvline(date, color="#777777", alpha=0.3, ls=":")
            if ax is axes[0]:
                ax.annotate(
                    note["text"][:35],
                    (date, 0.98),
                    xycoords=("data", "axes fraction"),
                    rotation=90,
                    va="top",
                    fontsize=7,
                )
        style_axis(ax, label)
        ax.legend(loc="upper left", fontsize=7, ncol=3)
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S", tz=timezone.utc))
    axes[1].set_xlabel("Desktop receive time (UTC); gaps are not interpolated")
    return fig, axes


def analysis_figure(
    groups,
    kind="scatter",
    wall_field="wall_cap_filtered",
    heater=0,
    include_flagged=False,
    figure=None,
    references=None,
    summaries=None,
):
    fig = figure or Figure(figsize=(11, 6), dpi=110, layout="constrained")
    fig.clear()
    axes = fig.subplots(1, 2)
    if kind == "scatter":
        for label, rows in groups.items():
            x, y = pair_values(rows, wall_field, include_flagged, heater)
            axes[0].scatter(x, y / 1000, s=10, alpha=0.55, label=label)
        style_axis(axes[0], "Gas resistance (kΩ)")
        axes[0].set_xlabel(wall_field + " (relative units)")
        axes[0].legend(fontsize=8)
        axes[0].set_title("Paired observations; association ≠ causation")
        axes[1].axis("off")
        axes[1].text(
            0.02,
            0.95,
            "Colors encode experimental ground truth,\nnot a firmware diagnosis.\n\nSee Statistics for full-data correlations.\nGraphs may use rendering downsampling.",
            va="top",
            fontsize=11,
        )
    elif kind in ("histogram", "box"):
        for axis, field in zip(axes, (wall_field, "gas_resistance_ohms")):
            arrays = []
            labels = []
            for label, rows in groups.items():
                vals = [
                    r[field]
                    for r in rows
                    if r.get(field) is not None
                    and valid_row(r, include_flagged)
                    and (
                        field != "gas_resistance_ohms"
                        or heater is None
                        or r.get("gas_heater_index") in (None, heater)
                    )
                ]
                if vals:
                    arrays.append(vals)
                    labels.append(label)
            if kind == "histogram":
                for label, values in zip(labels, arrays):
                    axis.hist(values, bins=25, alpha=0.45, label=label)
                axis.legend(fontsize=8)
                axis.set_ylabel("Count in plotted sample")
            elif arrays:
                axis.boxplot(arrays, tick_labels=labels, showfliers=True)
                axis.tick_params(axis="x", rotation=20)
            axis.set_xlabel(
                field
                + (" (Ω)" if field == "gas_resistance_ohms" else " (relative units)")
            )
            axis.grid(alpha=0.15)
    elif kind == "normalized":
        references = references or {}
        summaries = summaries or {}
        for label, rows in groups.items():
            if not rows:
                continue
            for field, key, linestyle in (
                (wall_field, "wall", "-"),
                ("gas_resistance_ohms", "gas", "--"),
            ):
                ref = references.get(key)
                if ref is None:
                    ref = summaries.get(label, {}).get(key, {}).get("mean")
                transformed = [
                    {**r, "_percent": percent(r.get(field), ref)}
                    for r in rows
                    if key != "gas" or r.get("gas_heater_index") in (None, heater)
                ]
                dates, values = timeline(transformed, "_percent")
                elapsed = [
                    (
                        d
                        - mdates.date2num(
                            datetime.fromtimestamp(
                                rows[0]["received_epoch"], timezone.utc
                            )
                        )
                    )
                    * 1440
                    for d in dates
                ]
                axes[0].plot(elapsed, values, linestyle, label=label + " " + key)
        axes[0].set_xlabel("Elapsed (minutes)")
        style_axis(axes[0], "% deviation from control / full session mean")
        axes[0].axhline(0, color=REFERENCE, ls=":")
        axes[0].legend(fontsize=7)
        axes[1].axis("off")
        axes[1].text(
            0.02,
            0.95,
            "Wall and gas share a normalized axis.\nSolid: wall response. Dashed: gas.\n\nReference: selected control means when available;\notherwise exact full-session means.\nZero references are undefined and remain missing.",
            va="top",
        )
    fig.suptitle("MoldSense · " + kind + " · heater step " + str(heater), fontsize=12)
    return fig, axes


def distribution_figure(
    distributions, kind, wall_field="wall_cap_filtered", figure=None
):
    fig = figure or Figure(figsize=(11, 6), layout="constrained")
    fig.clear()
    axes = fig.subplots(1, 2)
    for axis, field in zip(axes, (wall_field, "gas_resistance_ohms")):
        boxes = []
        labels = []
        for label, group in distributions.items():
            data = group.get(field, {})
            if not data.get("n"):
                continue
            title = label + " (N=" + str(data["n"]) + ")"
            if kind == "histogram":
                axis.stairs(data["counts"], data["edges"], label=title, linewidth=1.5)
            else:
                boxes.append({**data["box"], "label": title})
                labels.append(title)
        if kind == "box" and boxes:
            axis.bxp(boxes, showfliers=True)
            axis.tick_params(axis="x", rotation=20, labelsize=7)
        else:
            axis.legend(fontsize=7)
            axis.set_ylabel("Full-data observation count")
        axis.set_xlabel(
            field + (" (Ω)" if field == "gas_resistance_ohms" else " (relative units)")
        )
        axis.grid(alpha=0.15)
    fig.suptitle(
        "MoldSense · full-data "
        + kind
        + " (quartiles and counts use all selected observations)"
    )
    return fig, axes


def longitudinal_figure(records, summaries, figure=None):
    """Separate locations/materials and use actual session chronology, never selection order."""
    fig = figure or Figure(figsize=(11, 6), layout="constrained")
    fig.clear()
    axes = fig.subplots(2, 2)
    groups = {}
    for label, meta in records.items():
        key = (meta.get("location_name", "Unknown"), meta.get("material", "Unknown"))
        groups.setdefault(key, []).append(
            (datetime.fromisoformat(meta["started_at"]), label)
        )
    for (location, material), visits in groups.items():
        visits.sort()
        dates = [v[0] for v in visits]
        for ax, key, unit in zip(
            axes.flat,
            ("wall", "gas", "humidity", "risk"),
            ("relative units", "Ω", "% RH", "index 0–100"),
        ):
            values = [summaries[label][key]["mean"] for _, label in visits]
            ax.plot(dates, values, "o-", label=f"{location} · {material}")
            style_axis(ax, key + " (" + unit + ")")
            ax.xaxis.set_major_formatter(
                mdates.DateFormatter("%d %b %H:%M", tz=timezone.utc)
            )
            ax.tick_params(axis="x", rotation=20)
            ax.legend(fontsize=7)
    fig.suptitle("Repeated-location session means · session start time (UTC)")
    return fig, axes
