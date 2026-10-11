from dataclasses import replace
import unittest
import numpy as np
from config import EstimatorConfig, ExperimentConfig
from localization.placeholder import PlaceholderEstimator
from models.observation import Observation
from simulation.synthetic import generate_observations


class FailureTests(unittest.TestCase):
    def setUp(self):
        self.c = EstimatorConfig()
        self.receivers = ExperimentConfig().receivers
        self.obs = tuple(Observation(100, r.receiver_id, "test_emitter", 1) for r in self.receivers)
        self.engine = PlaceholderEstimator()

    def result(self, obs=None, receivers=None, config=None):
        return self.engine.estimate(self.obs if obs is None else obs,
                                   self.receivers if receivers is None else receivers,
                                   self.c if config is None else config)

    def test_zero_one_and_disabled(self):
        for obs in ((), self.obs[:1]):
            self.assertEqual(self.result(obs).status, "INSUFFICIENT_DATA")
        self.assertEqual(self.result(receivers=tuple(replace(r, enabled=False) for r in self.receivers)).status, "INSUFFICIENT_DATA")

    def test_stale_and_boundary_age(self):
        self.assertEqual(self.result(tuple(replace(o, timestamp=94) for o in self.obs)).status, "STALE_DATA")
        self.assertEqual(self.result(tuple(replace(o, timestamp=95) for o in self.obs)).status, "OK")
        mixed = (replace(self.obs[0], timestamp=90), *self.obs[1:])
        self.assertEqual(self.result(mixed).active_observation_count, 3)

    def test_invalid_measurements(self):
        for change in (dict(value=float("nan")), dict(value=float("inf")), dict(timestamp=101),
                       dict(receiver_id="unknown"), dict(unit="dBm")):
            self.assertEqual(self.result((replace(self.obs[0], **change), *self.obs[1:])).status, "INVALID_INPUT")

    def test_emitter_isolation(self):
        other = tuple(replace(o, emitter_id="wifi_other", value=float("nan")) for o in self.obs)
        self.assertEqual(self.result(other).status, "INSUFFICIENT_DATA")
        mixed = self.result(self.obs + other)
        self.assertEqual(mixed.active_observation_count, 4)
        np.testing.assert_array_equal(mixed.probability_grid, self.result().probability_grid)

    def test_placeholder_independent_of_values(self):
        changed = tuple(replace(o, value=o.value+1000) for o in self.obs)
        np.testing.assert_array_equal(self.result(changed).probability_grid, self.result().probability_grid)

    def test_normalized_grid(self):
        r = self.result()
        self.assertEqual(r.probability_grid.shape, (50, 50))
        self.assertAlmostEqual(r.probability_grid.sum(), 1)
        self.assertTrue(np.isfinite(r.probability_grid).all())
        self.assertTrue((r.probability_grid >= 0).all())

    def test_full_dropout(self):
        obs = generate_observations(self.receivers, "test_emitter", seed=42, timestamp=100,
                                    noise=.1, bias=0, dropout=1, base_value=1)
        self.assertEqual(obs, ())

    def test_invalid_grid_status(self):
        class Broken(PlaceholderEstimator):
            def _fixture(self, x, y, config):
                return np.zeros((len(y), len(x)))
        self.assertEqual(Broken().estimate(self.obs, self.receivers, self.c).status, "ESTIMATOR_FAILURE")

    def test_bad_config(self):
        for change in (dict(grid_resolution_m=0), dict(grid_resolution_m=3), dict(maximum_observation_age=-1)):
            self.assertEqual(self.result(config=replace(self.c, **change)).status, "INVALID_INPUT")

    def test_duplicates_and_quality(self):
        self.assertEqual(self.result((self.obs[0], self.obs[0])).status, "INVALID_INPUT")
        self.assertEqual(self.result(tuple(replace(o, quality="INVALID") for o in self.obs)).status, "INSUFFICIENT_DATA")
