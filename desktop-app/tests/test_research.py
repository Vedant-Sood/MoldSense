import csv, json, math, sys, tempfile, time, unittest, zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from moldsense_user.research.protocol import (
    Parser,
    parse_line,
    compatible,
    SequenceTracker,
)
from moldsense_user.research.database import Database, utc
from moldsense_user.research.acquisition import Acquisition, identify
from moldsense_user.research.statistics import (
    describe,
    percent,
    rolling,
    correlation,
    analyze_database,
    distributions_database,
    DEFAULT_SETTINGS,
)
from moldsense_user.research.exports import export_data, session_report
from moldsense_user.research.migration import import_legacy
from moldsense_user.research.plots import (
    timeline,
    time_figure,
    analysis_figure,
    longitudinal_figure,
)
import numpy as np


def packet(sequence=0, **values):
    return {
        "type": "reading",
        "protocol_version": 1,
        "device_id": "MOLDSENSE_TEST",
        "firmware_version": "1.0.0-rc1",
        "boot_id": "TEST_BOOT",
        "sequence": sequence,
        "uptime_ms": sequence * 1000,
        "wall_cap_raw": 100 - sequence * 0.01,
        "wall_cap_filtered": 100 - sequence * 0.01,
        "wall_moisture_index": sequence * 0.1,
        "wall_baseline": 100,
        "wall_deviation": -sequence * 0.01,
        "gas_resistance_ohms": 400000 + sequence * 100,
        "gas_observation_id": sequence,
        "gas_heater_index": 0,
        "temperature_c": 25,
        "humidity_percent": 50,
        "pressure_pa": 101325,
        "data_quality": "VALID",
        "air_valid": True,
        "wall_valid": True,
        "baseline_valid": True,
        "confidence": 66,
        "model_sha256": "NONE",
        **values,
    }


class ProtocolTests(unittest.TestCase):
    def test_partial_malformed_and_bounded(self):
        parser = Parser()
        raw = json.dumps(packet()).encode()
        self.assertEqual(parser.feed(raw[:12]), [])
        frames = parser.feed(raw[12:] + b"\n")
        self.assertEqual(frames[0].message["sequence"], 0)
        self.assertIsNotNone(parse_line("{bad}").error)
        self.assertIsNotNone(
            parse_line(json.dumps(packet(humidity_percent="wrong"))).error
        )
        self.assertIsNotNone(parse_line(json.dumps(packet(protocol_version=2))).error)
        self.assertIsNotNone(parser.feed(b"x" * 20000 + b"\n")[0].error)
        self.assertEqual(len(parser.buffer), 0)

    def test_huge_numeric_frame_is_rejected_without_losing_next_frame(self):
        parser = Parser()
        bad = json.dumps(packet(gas_resistance_ohms=10 ** 400)).encode()
        good = json.dumps(packet(1)).encode()
        frames = parser.feed(bad + b"\n" + good + b"\n")
        self.assertEqual(len(frames), 2)
        self.assertIsNotNone(frames[0].error)
        self.assertIsNone(frames[0].message)
        self.assertEqual(frames[1].message["sequence"], 1)

    def test_protocol_version_requires_integer(self):
        for version in (True, 1.0, "1", None):
            with self.subTest(version=version):
                frame = parse_line(json.dumps(packet(protocol_version=version)))
                self.assertEqual(frame.error, "PROTOCOL_MISMATCH")
        self.assertIsNone(parse_line(json.dumps(packet())).error)

    def test_sequence_and_boot(self):
        tracker = SequenceTracker()
        self.assertEqual(tracker.observe(packet(1)), ("OK", 0))
        self.assertEqual(tracker.observe(packet(4)), ("SEQUENCE_GAP", 2))
        self.assertEqual(tracker.observe(packet(4))[0], "DUPLICATE_OR_OUT_OF_ORDER")
        self.assertEqual(tracker.observe(packet(0, boot_id="new")), ("OK", 0))

    def test_production_firmware_serialization(self):
        fixture = Path(__file__).parent / "fixtures/firmware_readings.ndjson"
        frames = Parser().feed(fixture.read_bytes())
        self.assertEqual(len(frames), 2)
        self.assertTrue(all(f.message is not None for f in frames))
        self.assertIsNone(frames[0].message["gas_resistance_ohms"])
        self.assertEqual(frames[1].message["gas_resistance_ohms"], 420000)

    def test_serial_identification_without_hardware(self):
        class Link:
            closed = False

            def write(self, data):
                self.written = data

            def read(self, n):
                return (
                    json.dumps(packet(type="device_info", product="MoldSense")) + "\n"
                ).encode()

            def close(self):
                self.closed = True

        link = Link()
        found, info = identify("SIMULATED", opener=lambda _: link)
        self.assertIs(found, link)
        self.assertEqual(link.written, b"@1 PING\n")
        self.assertFalse(link.closed)
        with self.assertRaises(ValueError):
            identify("SIMULATED", "ANOTHER_DEVICE", lambda _: link)
        self.assertTrue(link.closed)

    def test_identification(self):
        info = packet(type="device_info", product="MoldSense")
        self.assertTrue(compatible(info))
        self.assertFalse(compatible({**info, "firmware_version": "2.0.0"}))
        self.assertFalse(compatible({**info, "product": "Other"}))


class StatisticsTests(unittest.TestCase):
    def test_descriptive(self):
        s = describe([1, 2, 3, 4, 5], 2)
        self.assertEqual(s["n"], 5)
        self.assertEqual(s["mean"], 3)
        self.assertEqual(s["median"], 3)
        self.assertAlmostEqual(s["variance"], 2.5)
        self.assertEqual(s["percent_difference"], 50)
        self.assertIsNone(percent(3, 0))
        self.assertIsNone(describe([])["mean"])
        self.assertTrue(math.isnan(rolling([1, None, 3], 2)[1]))

    def test_correlations(self):
        c = correlation(np.array([1, 2, 3]), np.array([6, 4, 2]))
        self.assertAlmostEqual(c["pearson"], -1)
        self.assertAlmostEqual(c["spearman"], -1)
        self.assertIsNone(
            correlation(np.array([1, 1, 1]), np.array([1, 2, 3]))["pearson"]
        )


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(self.tmp.name)
        self.exp = self.db.create_experiment("Synthetic test ONLY")
        sample = self.db.create_sample(
            "Synthetic control", "Lab", "Room", "Gypsum", label="CONTROL"
        )
        self.session = self.db.create_session(
            self.exp,
            sample,
            "Synthetic session",
            "MOLDSENSE_TEST",
            {"sample_interval_ms": 1000},
            DEFAULT_SETTINGS,
        )

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def ingest(self, n=20):
        frames = []
        for i in range(n):
            p = packet(i)
            frames.append((json.dumps(p), p, None, utc(), 1700000000 + i))
        self.db.ingest_batch(self.session, frames)

    def test_insert_duplicate_flags_groundtruth(self):
        self.ingest()
        self.ingest()
        self.assertEqual(self.db.count(self.session), 20)
        self.assertEqual(self.db.rows("SELECT COUNT(*) n FROM packets")[0]["n"], 40)
        p = packet(30, humidity_percent=200)
        self.db.ingest_batch(
            self.session, [(json.dumps(p), p, None, utc(), 1700000030)]
        )
        self.assertIn("IMPLAUSIBLE", self.db.query([self.session])[-1]["quality"])
        self.assertEqual(self.db.metadata(self.session)["ground_truth"], "CONTROL")

    def test_recovery_pause_and_reconnect(self):
        acq = Acquisition(self.db)
        acq.attach_session(self.session)
        acq.process(parse_line(json.dumps(packet(1))), 1700000001)
        acq.set_recording(False)
        acq.process(parse_line(json.dumps(packet(2))), 1700000002)
        self.assertEqual(self.db.count(self.session), 1)
        acq.set_recording(True)
        acq.process(
            parse_line(json.dumps(packet(4, boot_id="SECOND_BOOT"))), 1700000005
        )
        self.assertEqual(self.db.count(self.session), 2)
        self.db.event(self.session, "DISCONNECTED", {})
        self.assertEqual(self.db.recover()[0]["id"], self.session)

    def test_exact_statistics_export_report(self):
        self.ingest()
        self.db.annotate(self.session, "Synthetic annotation", 1700000005)
        summary = analyze_database(self.db, [self.session])
        self.assertEqual(summary["wall"]["n"], 20)
        self.assertAlmostEqual(summary["wall"]["mean"], 99.905)
        output = Path(self.tmp.name) / "export.csv"
        export_data(self.db, [self.session], output)
        self.assertEqual(
            len(
                list(
                    csv.DictReader(output.read_text(encoding="utf-8-sig").splitlines())
                )
            ),
            20,
        )
        output = Path(self.tmp.name) / "export.json"
        export_data(self.db, [self.session], output, "json")
        doc = json.loads(output.read_text())
        self.assertEqual(len(doc["readings"]), 20)
        self.assertEqual(len(doc["packets"]), 20)
        path = session_report(self.db, self.session, Path(self.tmp.name) / "report")
        self.assertTrue(path.exists())
        self.assertGreater((path.parent / "signals.svg").stat().st_size, 1000)

    def test_decimation_preserves_original(self):
        self.ingest(10000)
        rows = self.db.plot_rows(self.session, limit=600)
        self.assertLessEqual(len(rows), 606)
        self.assertEqual(self.db.count(self.session), 10000)
        self.assertEqual(len(self.db.query([self.session], limit=250, offset=250)), 250)

    def test_checked_log_transfer(self):
        acq = Acquisition(self.db)
        data = b"uptime_ms,rh\n1000,50\n"
        acq.process(
            parse_line(
                json.dumps(
                    packet(
                        type="log_chunk",
                        offset=0,
                        hex=data.hex(),
                        crc32=zlib.crc32(data),
                    )
                )
            )
        )
        acq.process(
            parse_line(
                json.dumps(
                    packet(
                        1,
                        type="log_complete",
                        bytes=len(data),
                        expected_bytes=len(data),
                    )
                )
            )
        )
        self.assertEqual(
            list((self.db.root / "device_logs").glob("*.csv"))[0].read_bytes(), data
        )
        with self.assertRaises(ValueError):
            acq.process(
                parse_line(
                    json.dumps(
                        packet(2, type="log_chunk", offset=0, hex=data.hex(), crc32=0)
                    )
                )
            )
        self.assertEqual(self.db.rows("SELECT COUNT(*) n FROM packets")[0]["n"], 3)

    def test_truncated_download_not_certified(self):
        acq = Acquisition(self.db)
        data = b"a"
        acq.process(
            parse_line(
                json.dumps(
                    packet(
                        type="log_chunk",
                        offset=0,
                        hex=data.hex(),
                        crc32=zlib.crc32(data),
                    )
                )
            )
        )
        with self.assertRaises(ValueError):
            acq.process(
                parse_line(
                    json.dumps(
                        packet(1, type="log_complete", bytes=1, expected_bytes=2)
                    )
                )
            )
        acq.close()
        self.assertEqual(len(list((self.db.root / "device_logs").glob("*.partial"))), 1)

    def test_full_distributions_and_profile_consistency(self):
        self.ingest(1000)
        result = distributions_database(self.db, [self.session])
        self.assertEqual(sum(result["gas_resistance_ohms"]["counts"]), 1000)
        rows = self.db.query([self.session], limit=20)
        for i, r in enumerate(rows):
            r["gas_heater_index"] = i % 2
        fig, axes = time_figure(
            rows, self.db.metadata(self.session), {"gas_heater_index": 0}
        )
        self.assertEqual(len(axes[1].lines[0].get_ydata()), 10)
        fig, axes = analysis_figure(
            {"test": rows}, "normalized", references={"wall": 100, "gas": 400000}
        )
        gas = axes[0].lines[1].get_ydata()
        self.assertEqual(len(gas), 10)
        self.assertAlmostEqual(gas[1], 0.05)

    def test_longitudinal_chronology_and_separation(self):
        records = {
            "late": {
                "started_at": "2026-09-14T00:00:00+00:00",
                "location_name": "A",
                "material": "Gypsum",
            },
            "early": {
                "started_at": "2026-09-01T00:00:00+00:00",
                "location_name": "A",
                "material": "Gypsum",
            },
            "other": {
                "started_at": "2026-09-02T00:00:00+00:00",
                "location_name": "B",
                "material": "Brick",
            },
        }
        summaries = {
            label: {k: {"mean": v} for k in ("wall", "gas", "humidity", "risk")}
            for label, v in [("late", 2), ("early", 1), ("other", 3)]
        }
        fig, axes = longitudinal_figure(records, summaries)
        self.assertEqual(list(axes.flat[0].lines[0].get_ydata()), [1, 2])
        self.assertEqual(len(axes.flat[0].lines), 2)

    def test_gap_rendering(self):
        self.ingest(4)
        rows = self.db.query([self.session])
        rows[2]["boot_id"] = "new"
        x, y = timeline(rows, "wall_cap_raw")
        self.assertTrue(any(math.isnan(v) for v in y))

    def test_legacy_missing_fields(self):
        source = Path(self.tmp.name) / "old.csv"
        source.write_text(
            "uptime_ms,gas_ohms,temperature_c\n100,450000,25\n200,440000,25\n"
        )
        ident = import_legacy(self.db, source)
        rows = self.db.query([ident])
        self.assertEqual(rows[0]["source"], "legacy")
        self.assertIsNone(rows[0]["wall_moisture_index"])
        self.assertEqual(import_legacy(self.db, source), ident)


if __name__ == "__main__":
    unittest.main()
