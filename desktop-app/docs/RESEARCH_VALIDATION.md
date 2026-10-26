> Historical September verification record. See [current import verification](../../docs/VERIFICATION.md) for checks rerun on this repository.

# Research application verification

Status: source application release candidate 2.0.0-rc1, protocol 1; tested on Windows 11/Python 3.13.9. Physical USB/sensor qualification is still required. No live ESP32 port was opened in this development run.

## Automated software checks

`python -m unittest discover -s tests -p test_*.py -v` passes **23 tests**: six preserved legacy tests and seventeen research tests. They cover the actual firmware-generated NDJSON fixture; fragmented/malformed/oversize frames; sequence gaps/duplicates/reboots; compatible identity and wrong-device refusal through a simulated serial link; descriptive values/correlations; exact full-data distributions; heater-step plot/normalization consistency; chronological longitudinal grouping; durable insertion/duplicate preservation; independent labels; acquisition pause/recovery; CSV/JSON/HTML/PNG/SVG export; legacy missing fields; and CRC/offset/length download checks including rejected truncation.

Run source UI smoke testing from the project root:

```powershell
.\.venv\Scripts\python.exe tests/ui_smoke.py
```

This uses only synthetic data with `autoconnect=False`, opens all eight views, draws live/scatter/normalized/histogram/box/longitudinal plots, exercises presentation and view pause, checks table pagination, then closes the app. It creates visibly labelled synthetic QA artifacts under `../outputs/moldsense_research_qa`. Figure exports were visually inspected; the UI check is a functional layout/rendering smoke test, not a pixel-perfect inspection of every Windows theme/resolution.

The launcher also accepts `--self-test <result.json>` for an offline installation check. It constructs the eight-view UI, draws Matplotlib, checks numerical dependencies/SQLite lifecycle, and explicitly confirms that no serial worker exists. The packaged Windows EXE passed this self-test on the development machine; its JSON result is included in release evidence. Repeat it on a clean destination machine before connecting an instrument. A successful source test does not by itself establish that every frozen dependency was bundled correctly.

## Scale test

`python tests/benchmark_research.py` creates and removes its own temporary synthetic database. It inserted 1,000,000 readings and their original packets, preserved all rows and checked the expected exact mean. Results on this machine:

| Operation | Result |
|---|---:|
| Batch insert | 151.28 seconds |
| Last 250-row table page | 0.37 seconds |
| Entire-session extrema plot query | 27.05 seconds |
| Rendered points | 2086 |
| Exact full-data statistics | 18.07 seconds |
| SQLite database size | 1,383,501,824 bytes |

This is not a measured one-million-packet USB run. Slow storage and full-history queries still need time, but execute outside the Tk event loop. Analysis arrays grow with selected data. The exact benchmark JSON and test logs are included in the release evidence.

## Physical and operational checks still required

1. Use a backed-up, explicitly authorized ESP32 and verify protocol/firmware/device IDs. Test driver-specific DTR/RTS reset behavior, initial discovery, multiple units and COM-port reassignment.
2. Collect dry/damp controls, valid baseline progress/failure/cancel, high RH without wet wall, brief spikes and unrelated VOCs. Independently record material/placement/ground truth. Do not treat synthetic QA charts as evidence.
3. Disconnect/reconnect while recording, reboot the ESP32, pause acquisition versus visualization, exit unexpectedly and resume deliberately. Check DB counts against firmware sequence/observation IDs; account for non-reading packets in sequence-gap calculations.
4. Exercise an actual full disk, permissions failure, corrupt database copy, USB packet truncation and interrupted log download on disposable copies. Confirm the application reports the condition and retains original archives; finite transport buffers may lose data during disk failure and must be reflected as gaps.
5. Run a 72-hour collection soak with UI interactions/export; monitor memory/CPU, disk latency and packet losses. Review report metadata against actual saved firmware/model/baseline identities.
6. On a clean Windows machine without Python, run the portable EXE self-test and workflow with a physical device. The executable is not signed and no installer/Startup behavior is added by the new build script.

For a publishable experiment, use stopped sessions for stable exports, freeze the analysis configuration, retain original packets and SHA-256 sidecars, and split independent physical samples/days for model validation. The risk index remains unvalidated even though its software arithmetic passes tests.
