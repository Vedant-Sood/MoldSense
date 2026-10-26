# Research extension assessment — 2026-09-14

KEEP: Python/Tkinter, local SQLite, pyserial, original archives and manifests, bundled capture readers, original dashboard as `--legacy`.

REFACTOR: the default entry point opens the research workspace; transport runs separately from Tk; plots use Matplotlib's scientific axes, interaction, and PNG/SVG export. A dedicated database sits beside the legacy database. Original values and packets are immutable records.

REMOVE from the new workflow: automatic post-download log deletion, consumer risk-first dashboard hierarchy, and blind command timeouts. The old implementation remains available for legacy firmware/archive retrieval.

ADD: versioned NDJSON, verified device identity, reconnect state, SQLite acquisition pipeline, experiments/sessions/samples/locations, baseline events, annotations, paired statistics, controls, range selection, downsampled rendering, paginated data, metadata-bearing exports and HTML reports.

Existing communication was human-readable STATUS plus FILES / FILE_DUMP hexadecimal delimiters. The new ESP32 project initially used guarded textual commands; it is being extended with protocol v1. Firmware versions must be explicitly checked. A legacy log is imported, never silently interpreted as a protocol-v1 acquisition.

The new request explicitly authorizes desktop session and wall-calibration controls, superseding the older dashboard's device-buttons-only policy. No desktop control resets BSEC or replaces an AI model. No Startup registration is added.
