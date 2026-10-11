import ast
from dataclasses import fields, replace
from pathlib import Path
import tempfile
import unittest
import numpy as np
from config import EstimatorConfig, ExperimentConfig
from experiments.baseline import run_experiment
from localization.placeholder import PlaceholderEstimator


class DataSeparationTests(unittest.TestCase):
    def test_estimator_receives_restricted_config_and_observations_only(self):
        class Spy(PlaceholderEstimator):
            def estimate(self, observations, receivers, config):
                self.received = (observations, receivers, config)
                return super().estimate(observations, receivers, config)
        spy = Spy()
        with tempfile.TemporaryDirectory() as tmp:
            run_experiment(ExperimentConfig(), "baseline", Path(tmp), spy, False)
        self.assertIs(type(spy.received[2]), EstimatorConfig)
        self.assertNotIn("test_emitter_x", {f.name for f in fields(spy.received[2])})
        self.assertEqual({f.name for f in fields(spy.received[0][0])},
                         {"timestamp", "receiver_id", "emitter_id", "value", "unit", "quality"})

    def test_changing_truth_does_not_change_estimate_or_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = run_experiment(ExperimentConfig(), "baseline", Path(tmp)/"a", make_plot=False)
            b = run_experiment(replace(ExperimentConfig(), test_emitter_x=20), "baseline", Path(tmp)/"b", make_plot=False)
            self.assertEqual(a["representative_position"], b["representative_position"])
            self.assertNotEqual(a["position_error_m"], b["position_error_m"])
            self.assertEqual((Path(tmp)/"a/baseline/observations.json").read_bytes(),
                             (Path(tmp)/"b/baseline/observations.json").read_bytes())

    def test_localization_has_no_truth_import_or_access(self):
        root = Path(__file__).resolve().parents[1]/"localization"
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn("ground_truth", node.module or "")
                    self.assertNotIn("ExperimentConfig", [n.name for n in node.names])
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, ("test_emitter_x", "test_emitter_y", "ground_truth"))
