# Data architecture and analysis contract

## Separation of responsibilities

`research/protocol.py` frames/validates NDJSON. `acquisition.py` owns the serial worker, identity/reconnect, requests, checked downloads and rolling observation windows. `database.py` is the durable record. `statistics.py` performs independent numerical analysis; `plots.py` creates figures without UI state. `exports.py` writes traceable artifacts. `migration.py` imports existing captures without editing them. The Tkinter shell is split into layout, actions and chart coordination. This extends the previous application instead of replacing its archive with a new framework.

Acquisition is independent of chart refresh. UI event overload may coalesce notifications but not committed measurements. SQLite commits each received frame/reading transaction with WAL and synchronous FULL; queued plot jobs use separate connections. The serial and command queues are bounded. A blocked disk can still delay collection; protocol sequence gaps make loss visible. Finite USB/OS buffers cannot guarantee lossless logging under indefinite storage failure. Original malformed input is retained up to the documented framing bound.

## Schema

The new schema is separate from the earlier dashboard database. Table names and responsibilities:

| Table | Content |
|---|---|
| experiments | Research project name, creation time, notes |
| locations | Reusable room, material, location description |
| samples | Sample identifier, location link, independent ground truth and notes |
| sessions | Experiment/sample/device, lifecycle, start/end, parameter snapshot, analysis version, source |
| devices | Last seen physical identity/configuration |
| firmware_versions, model_versions | Distinct version identities and associated device metadata |
| analysis_configs | Immutable settings JSON keyed by content hash |
| packets | Original text, receive UTC/epoch and parsing/sequence error, including non-reading packets |
| readings | Indexed original numeric measurements, validity, boot/sequence, separately named derived fields |
| events | Connection, interruption, command timeout and lifecycle events |
| calibrations | Device, session, firmware baseline identity and full calibration packet |
| annotations | Time/optional reading-linked researcher observations |
| imports | Source SHA-256, original path, target session and import time |
| summaries | Most recent generated session statistics and analysis version |

Uniqueness `(session_id, device_id, boot_id, sequence)` prevents duplicate reading insertion. Every duplicate frame is still kept in `packets`. Foreign keys link experiment/sample/session metadata. Time, quality and ID indexes support pagination and bounded row iteration. Additive numeric-column migration leaves existing rows unchanged. There is no drop-table migration and no delete-all command.

A session has ready/recording/paused/stopped/interrupted states. An unexpected exit marks active sessions interrupted on next start; deliberate resumption records a new boundary. Pause acquisition retains incoming packets but not new reading rows; pause visualization affects neither. Session/sample names and ground truth are metadata, not inference outputs. The UI currently assigns ground truth at session creation; use annotations for later adjudication and a new confirmed session rather than silently rewriting the recorded label.

## Measurement semantics

Touch/ADC units are not universal capacitance or moisture percentages. Relative wall index is firmware baseline-normalized; raw and filtered signals stay separately selectable. Gas is recorded in ohms, displayed in suitable units. Environmental readings, firmware scores and confidence are retained as emitted. A missing sensor is null/flagged; it is not a zero reading. Firmware owns filtering, baseline and risk calculation. Device/config/model/baseline IDs remain attached through exports.

One telemetry packet may hold the latest gas observation. Gas statistics count fresh observation IDs within each boot; AI analyses select a heater step, default 0. Air and wall statistics use valid stored snapshots. Samples during warm-up can still contain valid physical measurements; `WARMING_UP` is eligible for descriptive analysis, while driver-impossible/error/sequence-gap rows are excluded by default. `Include flagged` deliberately includes them for inspection. This setting is stored in analysis metadata; raw data never changes.

## Statistics and references

For finite accepted values: sample count, arithmetic mean, median, min/max, range, sample variance and SD (`ddof=1`), quartiles, coefficient of variation `100*SD/abs(mean)`, difference from reference and `100*(value-reference)/abs(reference)`. Undefined zero-reference percentages, zero-mean CV and insufficient-sample SD remain null. MAD flags use `abs(x-median) > 3*1.4826*MAD`; they are advisory and never remove transient events. Zero MAD does not justify deleting all different values.

Wall dry baseline is a measured local reference; session mean summarizes the selected session; a control mean comes from the explicitly selected control; a range mean comes from a chosen interval. Reference lines have different labels/styles. A wall-index baseline is zero only when a valid baseline exists. Gas reference lines never imply a diagnostic threshold. The optional wall alert is the instrument index alert at 25, not a universal moisture percentage.

Rolling means use up to 30 available observations, reset after missing measurements, communication gaps or baseline changes; gas has a separate window per heater step and deduplicates held observations. Rolling values are added in separate columns during collection, not substituted for original sensors. The fixed window is versioned in analysis policy; a future alternative smoothing method must use a new name/configuration and preserve original values.

Pearson and Spearman use finite paired wall/gas observations for the selected heater and quality policy. Constant or insufficient samples produce unavailable correlation. Pairing is by the telemetry snapshot containing a fresh gas result; asynchronous sensors and receive latency preclude claiming exact physical simultaneity. Results are descriptive; no causal or mold diagnosis follows.

Histograms/box quartiles use all selected eligible readings, not chart downsampling. Box whiskers follow 1.5 IQR; all outlier counts are retained, while rendering may cap displayed fliers at 2000. Time-series downsampling retains first/last and wall/gas bucket extrema; scatter may display a reduced sample and explicitly says so. Full-data correlations are reported separately. Normalized gas and wall traces share percent-deviation units against selected control means or exact full-session means.

Do not compute a confidence interval by treating every adjacent second as an independent replicate. `independent_ci` supplies a Student-t 95% interval for at least three independent replicate means, and `effect_size` supplies pooled-SD standardized difference for independent groups. They are library helpers, not an automatic significance claim from selected time-series rows. Validate independence, distribution/design and multiple-testing policy before inferential use.

## Reproducibility and exports

Each created session captures device/config, model, baseline, software version and settings. Device responses contain actual firmware settings; historical packets retain changes during a session. Analysis configurations are content-addressed. Figure/report sidecars record selected field, control, ranges, settings and metadata. Complete JSON includes original packets, indexed readings, events, annotations and calibration records. CSV is convenient for ML preprocessing but is not an AI-Studio raw-heater capture.

For ML use, split by physical wall/sample/day, not random neighboring rows. Keep UNKNOWN/blinded samples separate from confirmed labels, record independent confirmation, and include dry/damp and unrelated VOC controls. Do not use the firmware's heuristic prediction as ground-truth labels. Raw gas resistance is not a mold class.

Exports from stopped sessions provide stable inputs. Active exports use bounded ID watermarks and avoid infinite collection, but are not one cross-table point-in-time snapshot. Metadata and original packet tables should be retained with publication files. SHA-256 detects later changes; it does not authenticate experimental truth.

## Legacy migration

Legacy CSV and Bosch `.bmerawdata` originals are copied with their SHA-256 under `legacy_sources`; original archives are read only. Reimport of the same hash returns the prior imported session. Missing wall, calibration, environmental or clock fields remain absent/null. Legacy rows are marked `LEGACY_INCOMPLETE` until explicitly included for analysis. Original timestamps remain verbatim in the raw record; `received_at` is import time, not a fabricated historical measurement date. `received_epoch` orders rows on one time basis per file, recorded in a `LEGACY_TIME_BASIS` event: device UTC when every row has a set clock, otherwise uptime offsets from import time (continuing across uptime restarts), otherwise one second per row. This keeps plots and time ranges in their original shape. Inspect source units/profile before comparison. An import that fails part-way is removed so it can be retried; its original source copy is kept for audit.

## Performance boundaries

A one-million-reading/one-million-packet synthetic benchmark produced a 1.38 GB database; insertion 151.28 s, last table page 0.37 s, extrema plot query 27.05 s, exact statistics 18.07 s. This is a batch benchmark, not measured USB throughput or a device soak. Read-only analysis is off the Tk event thread. Exact quantiles/correlations use compact arrays proportional to selected rows; unbounded datasets still need sufficient RAM/disk. No claim of unlimited storage or instantaneous full-history analysis is made.
