from dataclasses import replace
from pathlib import Path
import csv
import json
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

from config import ExperimentConfig
from evaluation.aggregation import (trial_row, summarize, collect_overconfident,
    TRIAL_FIELDS, SUMMARY_FIELDS, CALIBRATION_LABEL)
from evaluation.comparison import compare_summaries
from experiments.baseline import run_experiment
from experiments.validation_harness import (run_batch, read_trials, regenerate_reports,
    replay_manifest, config_from_manifest)


def make_row(index, error=1., status="OK", inside_50=False, inside_90=True, over=False):
    return trial_row(index, 42+index, "baseline", dict(status=status, position_error_m=error,
        region_50_area_m2=10., region_90_area_m2=20.,
        ground_truth_inside_50_region=inside_50, ground_truth_inside_90_region=inside_90,
        processing_time_ms=float(index+1), active_observation_count=4, overconfident_failure=over))


class AggregationTests(unittest.TestCase):
    def test_statistics(self):
        rows = [make_row(i, float(e)) for i, e in enumerate((1, 2, 3, 4))]
        s = summarize(rows, "baseline")
        self.assertEqual(s["position_error_mean_m"], 2.5)
        self.assertEqual(s["position_error_median_m"], 2.5)
        self.assertAlmostEqual(s["position_error_std_m"], np.sqrt(1.25))
        self.assertAlmostEqual(s["position_error_p90_m"], 3.7)
        self.assertAlmostEqual(s["position_error_p95_m"], 3.85)
        self.assertEqual(s["position_error_max_m"], 4)
        self.assertEqual(s["region_50_area_median_m2"], 10)
        self.assertEqual(s["region_90_area_median_m2"], 20)
        self.assertEqual(s["processing_time_median_ms"], 2.5)

    def test_coverage_valid_denominator(self):
        rows = [make_row(0, inside_50=True), make_row(1), make_row(2, status="STALE_DATA")]
        s = summarize(rows, "baseline")
        self.assertEqual(s["coverage_50_pct"], 50)
        self.assertEqual(s["coverage_90_pct"], 100)
        self.assertEqual(s["calibration_status"], CALIBRATION_LABEL)

    def test_failed_accounting(self):
        rows = [make_row(0), make_row(1, status="INVALID_INPUT"), make_row(2, status="INVALID_INPUT")]
        s = summarize(rows, "baseline")
        self.assertEqual(s["valid_trial_count"], 1)
        self.assertEqual(s["failed_trial_count"], 2)
        self.assertEqual(s["status_INVALID_INPUT_count"], 2)
        self.assertAlmostEqual(s["failure_rate_pct"], 200/3)
        self.assertAlmostEqual(sum(v for k,v in s.items() if k.startswith("status_") and k.endswith("_pct")), 100)

    def test_overconfidence_collection(self):
        rows = [make_row(0, over=True), make_row(1), make_row(2, over=True)]
        self.assertEqual([r["trial_id"] for r in collect_overconfident(rows)], [0, 2])
        self.assertEqual(summarize(rows, "baseline")["overconfident_failure_count"], 2)

    def test_empty_and_all_failed(self):
        for rows in ([], [make_row(0, status="ESTIMATOR_FAILURE")]):
            s = summarize(rows, "baseline")
            self.assertEqual(s["valid_trial_count"], 0)
            self.assertIsNone(s["coverage_50_pct"])
            self.assertIsNone(s["position_error_mean_m"])
            self.assertIsNone(s["processing_time_median_ms"])
        self.assertIsNone(summarize([], "baseline")["failure_rate_pct"])
        self.assertEqual(summarize([make_row(0, status="STALE_DATA")], "baseline")["failure_rate_pct"], 100)

    def test_invalid_ok_metrics_rejected(self):
        row = make_row(0)
        row["position_error_m"] = float("nan")
        with self.assertRaises(ValueError):
            summarize([row], "baseline")


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Numeric/contract tests do not need to repeatedly render the same figures.
        self.plot_patch = patch("experiments.validation_harness.create_validation_plots")
        self.plot_patch.start()
        self.addCleanup(self.plot_patch.stop)

    def batch(self, out="a", n=3, scenarios=("baseline",), executor=run_experiment):
        return run_batch(ExperimentConfig(), scenarios, 42, n, self.root/out, executor)

    def test_monte_carlo_reproducibility(self):
        a, sa = self.batch("a", scenarios=("baseline", "dropout", "stale"))
        b, sb = self.batch("b", scenarios=("baseline", "dropout", "stale"))
        for rows in (a,b):
            for row in rows:
                row.pop("processing_time_ms")
        for summaries in (sa,sb):
            for summary in summaries:
                summary.pop("processing_time_median_ms")
                summary.pop("processing_time_p90_ms")
        self.assertEqual(a,b)
        self.assertEqual(sa,sb)

    def test_csv_schema_and_roundtrip(self):
        rows, summaries = self.batch()
        self.assertEqual(read_trials(self.root/"a/trials.csv"), rows)
        for name, fields in (("trials.csv", TRIAL_FIELDS), ("summary.csv", SUMMARY_FIELDS)):
            with (self.root/"a"/name).open(newline="") as f:
                self.assertEqual(next(csv.reader(f)), list(fields))
        with (self.root/"a/overconfident_failures.csv").open(newline="") as f:
            self.assertEqual(len(list(csv.DictReader(f))), 3)

    def test_continue_after_exception(self):
        def fails_once(config, *args, **kwargs):
            if config.random_seed == 43:
                raise RuntimeError("deliberate test failure")
            return run_experiment(config, *args, **kwargs)
        rows, summaries = self.batch(executor=fails_once)
        self.assertEqual([r["status"] for r in rows], ["OK", "ESTIMATOR_FAILURE", "OK"])
        self.assertEqual(rows[1]["exception_type"], "RuntimeError")
        self.assertEqual(summaries[0]["failed_trial_count"], 1)

    def test_invalid_output_is_failure(self):
        def invalid(*args, **kwargs):
            return {"status": "OK", "position_error_m": float("nan")}
        rows, summary = self.batch(executor=invalid)
        self.assertEqual(summary[0]["failed_trial_count"], 3)
        self.assertTrue(all(r["exception_type"] == "ValueError" for r in rows))

    def test_manifest_and_replay(self):
        rows, _ = self.batch()
        path = self.root/"a/experiment_manifest.json"
        manifest = json.loads(path.read_text())
        self.assertEqual(manifest["number_of_trials_per_scenario"], 3)
        self.assertEqual(manifest["seed_end_inclusive"], 44)
        self.assertIn("numpy", manifest["dependency_versions"])
        self.assertIn("localization/placeholder.py", manifest["source_sha256"])
        self.assertEqual(config_from_manifest(manifest), ExperimentConfig())
        replayed, _ = replay_manifest(path, self.root/"replay")
        for collection in (rows, replayed):
            for row in collection:
                row.pop("processing_time_ms")
        self.assertEqual(rows, replayed)

    def test_report_does_not_rerun(self):
        _, summaries = self.batch()
        with patch("experiments.validation_harness.run_experiment", side_effect=AssertionError("must not run")):
            self.assertEqual(regenerate_reports(self.root/"a"), summaries)

    def test_empty_batches_and_all_failed(self):
        for out, n, scenarios in (("zero",0,("baseline",)), ("none",0,()), ("failed",3,("stale",))):
            rows, summaries = self.batch(out,n,scenarios)
            self.assertTrue((self.root/out/"trials.csv").is_file())
            self.assertTrue(all(s["valid_trial_count"] == 0 for s in summaries))
            regenerate_reports(self.root/out)

    def test_comparison(self):
        self.batch("a")
        self.batch("b")
        rows = compare_summaries(self.root/"a/summary.csv", self.root/"b/summary.csv", self.root/"comparison.csv")
        for row in rows:
            if row["metric"] != "processing_time_median_ms":
                self.assertEqual(row["candidate_minus_baseline"], 0)
        self.assertEqual(len(rows), 8)

    def test_comparison_missing_scenario(self):
        self.batch("a")
        self.batch("b", scenarios=("stale",))
        rows = compare_summaries(self.root/"a/summary.csv", self.root/"b/summary.csv", self.root/"comparison.csv")
        self.assertTrue(all(r["candidate_minus_baseline"] is None for r in rows))

    def test_comparison_delta_sign_and_percentage_points(self):
        self.batch("a")
        self.batch("b")
        path = self.root/"b/summary.csv"
        with path.open(newline="") as stream:
            saved = list(csv.DictReader(stream))
        saved[0]["position_error_median_m"] = str(float(saved[0]["position_error_median_m"])+2)
        saved[0]["coverage_90_pct"] = "25"
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=SUMMARY_FIELDS)
            writer.writeheader()
            writer.writerows(saved)
        rows = compare_summaries(self.root/"a/summary.csv", path, self.root/"comparison.csv")
        by_metric = {r["metric"]: r for r in rows}
        self.assertAlmostEqual(by_metric["position_error_median_m"]["candidate_minus_baseline"], 2)
        self.assertEqual(by_metric["coverage_90_pct"]["candidate_minus_baseline"], 25)
        self.assertEqual(by_metric["coverage_90_pct"]["unit"], "percentage_points")

    def test_empty_and_failed_plot_files(self):
        from visualization.validation_plots import create_validation_plots
        for name, rows in (("empty", []), ("failed", [make_row(0, status="STALE_DATA")])):
            output = self.root/name
            output.mkdir()
            create_validation_plots(rows, [summarize(rows, "baseline")], output)
            images = list(output.glob("*.png"))
            self.assertEqual(len(images), 4)
            self.assertTrue(all(p.stat().st_size > 1000 for p in images))

    def test_invalid_trial_count(self):
        with self.assertRaises(ValueError):
            self.batch(n=-1)

    def test_report_rejects_tampered_identity(self):
        self.batch()
        path = self.root/"a/experiment_manifest.json"
        manifest = json.loads(path.read_text())
        manifest["seed_start"] = 100
        path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            regenerate_reports(self.root/"a")
