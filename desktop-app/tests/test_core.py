import sys, tempfile, unittest, json
from unittest.mock import patch, Mock
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from moldsense_user.analysis import analyze, build_baseline, metric_value, overall_risk
from moldsense_user.device import is_log
from moldsense_user.datasets import build_catalog
from moldsense_user.references import bundled_capture_rows, bundled_files, tailored_cap_comparison
from moldsense_user.storage import Store

class CoreTests(unittest.TestCase):
    def setUp(self):
        # Generated test-only signals; no historical instrument data is required.
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        reference_directory = patch("moldsense_user.references.bundled_directory", return_value=directory)
        reference_directory.start()
        self.addCleanup(reference_directory.stop)
        keys = ["timestamp_since_poweron", "temperature", "pressure", "relative_humidity",
                "resistance_gassensor", "heater_profile_step_index", "scanning_cycle_index"]
        for name, gas in [("cap_1", 1000), ("cap_2", 2000), ("cap_1_tailored_to_cap_2", 1000)]:
            document = {
                "rawDataHeader": {"seedPowerOnOff": "SYNTHETIC TEST ONLY"},
                "rawDataBody": {
                    "dataColumns": [{"key": key} for key in keys],
                    "dataBlock": [[i * 1000, 25, 1013, 50, gas, i % 10, i // 10] for i in range(20)],
                },
            }
            (directory / (name + ".bmerawdata")).write_text(json.dumps(document), encoding="utf-8")

    def test_missing_optional_references(self):
        with tempfile.TemporaryDirectory() as empty, patch(
            "moldsense_user.references.bundled_directory", return_value=Path(empty)
        ):
            self.assertEqual(bundled_capture_rows(), {})
            self.assertIsNone(tailored_cap_comparison())
            with tempfile.TemporaryDirectory() as data:
                store = Store(data)
                self.assertEqual(build_catalog(store), [])
                store.db.close()

    def test_reference_profiles_without_shared_steps(self):
        row = {"gas_ohms": 1000, "temperature_c": 25, "humidity_percent": 50, "pressure_pa": 1013}
        captures = {"Cap 1 Tailored To Cap 2": [{**row, "heater_step": 0}],
                    "Cap 2": [{**row, "heater_step": 1}]}
        with patch("moldsense_user.references.bundled_capture_rows", return_value=captures):
            self.assertIsNone(tailored_cap_comparison())

    def test_legacy_overview_without_references(self):
        from moldsense_user.app import MoldSenseApp
        app = SimpleNamespace(deviations=[], rows=[], catalog=[], cap_comparison=None,
            risk_badge=Mock(), risk_heading=Mock(), risk_text=Mock(),
            stat_values={key: Mock() for key in ("readings", "datasets", "deviations", "baseline")},
            recent_tree=Mock(), compare_value=Mock(), compare_environment=Mock())
        app.recent_tree.get_children.return_value = ()
        MoldSenseApp._refresh_overview(app, {})
        app.compare_value.configure.assert_called_once_with(text="Not available")
        self.assertEqual(MoldSenseApp._reference_findings(app), [])

    def test_baseline_and_deviation(self):
        rows=[{"iaq":"50","iaq_accuracy":"3","temperature_c":"24","humidity_percent":"45","pressure_pa":"1002","gas_ohms":"80000","uptime_ms":str(i*60000)} for i in range(8)]
        baseline=build_baseline(rows); self.assertEqual(baseline["iaq"]["median"],50)
        rows.append({"iaq":"100","iaq_accuracy":"3","temperature_c":"24","humidity_percent":"82","pressure_pa":"1002","gas_ohms":"80000","uptime_ms":"540000"})
        deviations=analyze(rows,baseline); self.assertTrue(any(x.metric=="humidity_percent" and x.severity=="High" for x in deviations)); self.assertEqual(overall_risk(deviations)[0],"HIGH")
    def test_pressure_conversion(self): self.assertEqual(metric_value({"raw_pressure_pa":"100600"},"pressure_pa"),1006)
    def test_delete_allowlist(self):
        self.assertTrue(is_log("/environment.csv")); self.assertTrue(is_log("/cap_3.bmerawdata")); self.assertFalse(is_log("/bsec3_state.bin")); self.assertFalse(is_log("/../environment.csv"))
    def test_archive_manifest_and_csv(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(temp); payload=b"iaq,temperature_c,humidity_percent,pressure_pa,gas_ohms\n50,24,45,1002,80000\n"
            path,digest=store.archive("/environment.csv",payload,"COM3")
            self.assertTrue(path.exists()); self.assertEqual(len(digest),64); self.assertEqual(len(store.csv_rows()),1); self.assertTrue(path.with_suffix(".csv.manifest.json").exists())
            again,_digest=store.archive("/environment.csv",payload,"COM3")
            self.assertEqual(again,path); self.assertEqual(len(store.csv_rows()),1); self.assertEqual(len(store.imports()),1)
            store.db.close()
    def test_bundled_cap_samples(self):
        samples=bundled_capture_rows()
        self.assertEqual(len(samples["Cap 1"]),20); self.assertEqual(len(samples["Cap 2"]),20)
        self.assertEqual(len(samples["Cap 1 Tailored To Cap 2"]),20)
        self.assertIn("gas_ohms",samples["Cap 1"][0])
        comparison=tailored_cap_comparison()
        self.assertEqual(comparison["rows"],20); self.assertEqual(len(comparison["steps"]),10)
        self.assertAlmostEqual(comparison["gas_deviation"],200/3,places=2)
        self.assertEqual(len(bundled_files()),3)
    def test_customer_dataset_catalog(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(temp); catalog=build_catalog(store)
            self.assertEqual(len(catalog),3)
            tailored=next(item for item in catalog if "Tailored" in item.name)
            self.assertEqual(tailored.readings,20)
            self.assertTrue(tailored.supports("gas_ohms"))
            self.assertFalse(tailored.supports("iaq"))
            store.db.close()

if __name__=="__main__": unittest.main()
