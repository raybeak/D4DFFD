import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from config import ExperimentConfig
from experiments.baseline import run_experiment, SCENARIOS


class ReproducibilityTests(unittest.TestCase):
    def test_repeated_scenarios(self):
        with tempfile.TemporaryDirectory() as tmp:
            for scenario in SCENARIOS:
                with self.subTest(scenario=scenario):
                    first = run_experiment(ExperimentConfig(), scenario, Path(tmp)/"a", make_plot=False)
                    second = run_experiment(ExperimentConfig(), scenario, Path(tmp)/"b", make_plot=False)
                    first.pop("processing_time_ms")
                    second.pop("processing_time_ms")
                    self.assertEqual(first, second)
                    self.assertEqual((Path(tmp)/"a"/scenario/"observations.json").read_bytes(),
                                     (Path(tmp)/"b"/scenario/"observations.json").read_bytes())

    def test_seed_changes_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            for seed in (1, 2):
                run_experiment(replace(ExperimentConfig(), random_seed=seed), "baseline", Path(tmp)/str(seed), make_plot=False)
            self.assertNotEqual((Path(tmp)/"1/baseline/observations.json").read_bytes(),
                                (Path(tmp)/"2/baseline/observations.json").read_bytes())
