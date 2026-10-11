from dataclasses import replace
import math
import unittest
import numpy as np
from config import EstimatorConfig, EvaluationThresholds
from evaluation.metrics import model_region, contains, evaluate
from localization.interface import LocalizationResult, Status, validate_grid
from models.ground_truth import GroundTruth


class MetricTests(unittest.TestCase):
    def result(self):
        return LocalizationResult(np.array([[1., 0.], [0., 0.]]), np.array([1., 3.]),
                                  np.array([1., 3.]), (1., 1.), Status.OK, 4, 100, "e", 2)

    def test_euclidean_error_and_overconfidence(self):
        m = evaluate(self.result(), GroundTruth(100, "e", 4, 5), EvaluationThresholds(4, 5), 0)
        self.assertEqual(m["position_error_m"], 5)
        self.assertEqual(m["region_90_area_m2"], 4)
        self.assertTrue(m["overconfident_failure"])

    def test_strict_threshold(self):
        m = evaluate(self.result(), GroundTruth(100, "e", 4, 5), EvaluationThresholds(5, 4), 0)
        self.assertFalse(m["overconfident_failure"])

    def test_regions_and_ties(self):
        p = np.array([[0.4, 0.3], [0.2, 0.1]])
        self.assertEqual(model_region(p, .5, 4).cell_count, 2)
        self.assertEqual(model_region(p, .9, 4).area_m2, 12)
        self.assertEqual(model_region(np.ones((2, 2))/4, .5, 1).cell_count, 4)
        self.assertEqual(model_region(p, 1, 1).cell_count, 4)

    def test_region_footprints(self):
        r = self.result()
        region = model_region(r.probability_grid, .9, 4)
        self.assertTrue(contains(region, r, GroundTruth(100, "e", 0, 0)))
        self.assertFalse(contains(region, r, GroundTruth(100, "e", 2, 1)))
        self.assertFalse(contains(region, r, GroundTruth(100, "e", -0.1, 1)))
        all_cells = model_region(np.ones((2, 2))/4, .9, 4)
        self.assertTrue(contains(all_cells, r, GroundTruth(100, "e", 4, 4)))

    def test_invalid_grids(self):
        for p in (np.zeros((2, 2)), np.array([[np.nan, 0], [0, 1]]),
                  np.array([[np.inf, 0], [0, 0]]), np.array([[2., -1.], [0, 0]]), np.ones((3, 2))/6):
            with self.subTest(grid=p), self.assertRaises(ValueError):
                validate_grid(p, np.array([1, 2]), np.array([1, 2]))

    def test_failure_not_scored(self):
        r = replace(self.result(), status=Status.INSUFFICIENT_DATA, probability_grid=None, representative_position=None)
        m = evaluate(r, GroundTruth(100, "e", 1, 1), EvaluationThresholds(), 0)
        self.assertIsNone(m["position_error_m"])
        self.assertIsNone(m["overconfident_failure"])

    def test_invalid_result_failure(self):
        r = self.result()
        r.probability_grid[:] = 0
        self.assertEqual(evaluate(r, GroundTruth(100, "e", 1, 1), EvaluationThresholds(), 0)["status"], "ESTIMATOR_FAILURE")

    def test_truth_identity_time_checked(self):
        for truth in (GroundTruth(100, "other", 1, 1), GroundTruth(99, "e", 1, 1)):
            with self.assertRaises(ValueError):
                evaluate(self.result(), truth, EvaluationThresholds(), 0)
