> Historical verification record from September 2026. Current import checks are in [VERIFICATION.md](../../../../docs/VERIFICATION.md).

# Verification and hardware release gates

Software verification completed 2026-09-14. This is a release candidate, not a claim of field-qualified mold detection. No ESP32 serial port was opened and no firmware was flashed in this implementation.

## Checks completed

- Real ESP32 build: Arduino CLI 1.5.1, Espressif Arduino core 3.3.10, DOIT ESP32 DEVKIT V1. Flash 465556/1310720 bytes (35%); global RAM 47508/327680 bytes (14%). Runtime vendor allocations, stack peaks and heap fragmentation require physical measurement; the linker RAM number is not a soak-test result.
- Actual portable C++ production modules compiled/run with Zig 0.13.0 as the host C++ compiler: **624 assertions passed**. Risk/temporal model, classifier gates, wall filtering, calibration, CRC, dual-slot persistence, torn writes, independent BSEC state, protected log deletion and checked dump reads are exercised.
- The actual firmware serializer emitted a two-packet fixture containing missing/null and valid measurements; the desktop parser ingested it. This is an integration test, not a synthetic reimplementation of serialization.
- Desktop **23 tests passed** for protocol, statistics, data integrity, duplicate/gap/reboot handling, exports, reports, legacy migration and checked log downloads. Eight UI views and all analysis types passed an offline synthetic smoke test. Scientific time-series and scatter exports were visually inspected.
- One-million-row benchmark and timings are recorded in the companion desktop validation guide.

Reproduce host tests from the repository root:

```powershell
python firmware/esp32/MoldSense/tools/run_tests.py --compiler g++
```

Or provide a compatible installed C++ compiler as supported by the runner. The firmware compilation command is in README.md. Host Preferences/LittleFS/I/O are fault-injection mocks: they validate application logic, not ESP32 flash electrical behavior. PlatformIO is supplied as an alternate configuration but was not compiled in this run.

## Bench acceptance sequence (not yet performed)

1. Record board/ESP32 variant, flash map, library/model hashes, wiring, supply voltage and probe assembly. Back up the existing full flash and files into old_data with byte counts/hashes before any upload. Verify recovery tooling and retain the previous working binary.
2. Flash only with explicit device authorization. Capture boot SELF_TEST, STATUS, SENSOR_INFO, MODEL_INFO and GET_BASELINE. Confirm I2C addresses and actual OLED pixels. Confirm pressure near local physical pressure, not 100-fold error; compare temperature/RH against a reference in a stable enclosure.
3. Test both switches: bounce, boot while ON, OFF/ON arming, cancellation and detail mode. Holding baseline ON must not repeatedly overwrite calibration. Time calibration progress and verify stable-reference mean/median/SD and rejection of handling/noisy conditions.
4. Power-cycle after a successful baseline save and verify exact baseline ID/statistics restore. Independently allow BSEC to reach accuracy and checkpoint; record state identity and restore status. Recalibrate the wall and prove the BSEC blob/profile/state fingerprint did not change due to that action.
5. Interrupt power during baseline/BSEC writes repeatedly on a sacrificial unit. Boot must load one intact compatible slot or explicitly report unavailable/corrupt, never quietly accept bad data. Characterize actual brownout/reset behavior.
6. Disconnect/reconnect BME and OLED separately; shorted/stuck bus handling must not permanently hang the loop. No unavailable air/gas evidence should be reported as zero risk. Confirm retry recovery. Probe open/saturation/noise tests must be documented; a bare touch plate cannot guarantee open-wire detection, so add a contact/connectivity fixture if that fault must be conclusively detected.
7. Conduct a minimum 72 h stationary soak with serial telemetry/logging enabled. Monitor reset cause, free/minimum heap, sample/sequence loss, UI latency, BSEC state-save frequency, storage-full behavior and UART load. STATUS exposes packet drops, state, current/minimum free heap and reset reason for the qualification record. Check 32-bit wrap by test-clock injection (already host-tested), not by shortening real timing constants unnoticed.
8. If optional LittleFS logging is needed, test mount failure without formatting, full partition, malformed final row after power loss, download interruption/CRC rejection, exact final length, and CLEAR_LOG touching only its named file. Keep old capture files present during isolation tests.

## Scientific experiments

| Test | Required interpretation / expected software response |
|---|---|
| Dry same-material reference, normal RH | Near-zero wall index; low environment component; absence of mold is not certified |
| Wetted same-material coupon | Sustained signed wall deviation and rising relative index; repeatable effect versus independent moisture measurement |
| High air RH with dry plate/coupon | Environment increases with duration; wall stays near baseline; no automatic mold detection |
| Brief RH spike | Small transient component; no CRITICAL from a single spike |
| Sustained high RH | Gradually accumulated observed exposure; missing/offline hours are excluded |
| Unrelated VOC event | Raw gas may change; raw gas is never translated directly to mold probability |
| No trained model | Class probability unavailable, explicit NOT TRAINED, confidence reduced |
| Model with wrong mapping/profile/state | Rejected or unavailable classification; no silently relabelled class |
| Condensation | Without a surface probe: unavailable. With measured surface temperature below dew point: events and exposure tracked |

Record control/test ground truth independently, repeat across materials/placements/days, include blind samples, and keep full raw archives. A trained classification model needs held-out physical samples and confounder challenges before enabling its validated flag. Assess false positives/negatives and probability calibration. The heuristic fusion index itself still needs outcome-labelled calibration even if its VOC component is validated.

## Release decision

The compiled software and automated tests support review and bench deployment. Final production acceptance additionally requires the electrical/probe characterization, long-run fault tests, enclosure compensation, model validation (if used), licensing review and intended-use evidence above. Do not describe the current index as a measured probability that mold is present behind a wall.
