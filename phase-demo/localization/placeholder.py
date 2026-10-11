"""PLACEHOLDER / NOT VALIDATED / NOT A REAL RF LOCALIZATION ALGORITHM.

Returns a fixed, area-centered display fixture, independent of measured values,
receiver geometry, and ground truth. OK means the software contract succeeded.
"""
from typing import Sequence
import math
import numpy as np
from config import EstimatorConfig
from models.observation import Observation
from models.receiver import Receiver
from localization.interface import LocalizationResult, Status, validate_grid


class PlaceholderEstimator:
    def estimate(self, observations: Sequence[Observation], receivers: Sequence[Receiver],
                 config: EstimatorConfig) -> LocalizationResult:
        def failure(status: Status, message: str, count: int = 0) -> LocalizationResult:
            return LocalizationResult(None, np.array([]), np.array([]), None, status,
                                      count, config.evaluation_timestamp, config.emitter_id,
                                      config.grid_resolution_m, message)
        try:
            config.validate()
        except (ValueError, TypeError) as exc:
            return failure(Status.INVALID_INPUT, str(exc))
        ids = [r.receiver_id for r in receivers]
        if len(ids) != len(set(ids)) or any(not r.receiver_id or not math.isfinite(r.x) or not math.isfinite(r.y) for r in receivers):
            return failure(Status.INVALID_INPUT, "Invalid or duplicate receiver metadata")
        lookup = {r.receiver_id: r for r in receivers}
        selected = [o for o in observations if o.emitter_id == config.emitter_id]
        counts = dict(ignored_emitter=len(observations)-len(selected), disabled=0, stale=0, bad_quality=0)
        active = []
        for obs in selected:
            if obs.receiver_id not in lookup:
                return failure(Status.INVALID_INPUT, "Unknown receiver_id")
            if not lookup[obs.receiver_id].enabled:
                counts["disabled"] += 1
                continue
            if not math.isfinite(obs.value) or not math.isfinite(obs.timestamp) or obs.unit != "synthetic_unit":
                return failure(Status.INVALID_INPUT, "Nonfinite observation or wrong unit")
            age = config.evaluation_timestamp - obs.timestamp
            if age < 0:
                return failure(Status.INVALID_INPUT, "Future observation timestamp")
            if age > config.maximum_observation_age:
                counts["stale"] += 1
                continue
            if obs.quality != "VALID":
                counts["bad_quality"] += 1
                continue
            active.append(obs)
        if len(active) < 2:
            status = Status.STALE_DATA if not active and counts["stale"] else Status.INSUFFICIENT_DATA
            result = failure(status, "Placeholder contract requires two distinct valid receivers", len(active))
            result.diagnostics = counts
            return result
        if len({o.receiver_id for o in active}) != len(active):
            return failure(Status.INVALID_INPUT, "Only one observation per receiver per snapshot")
        step = config.grid_resolution_m
        x = (np.arange(round(config.area_width_m / step)) + 0.5) * step
        y = (np.arange(round(config.area_height_m / step)) + 0.5) * step
        try:
            grid = self._fixture(x, y, config)
            validate_grid(grid, x, y)
        except (ValueError, FloatingPointError, OverflowError) as exc:
            return failure(Status.ESTIMATOR_FAILURE, str(exc), len(active))
        iy, ix = np.unravel_index(np.argmax(grid), grid.shape)
        return LocalizationResult(grid, x, y, (float(x[ix]), float(y[iy])), Status.OK,
                                  len(active), config.evaluation_timestamp, config.emitter_id,
                                  step, "PLACEHOLDER - NOT VALIDATED", counts)

    def _fixture(self, x: np.ndarray, y: np.ndarray, config: EstimatorConfig) -> np.ndarray:
        """Fixed bell-shaped display fixture, NOT an observation likelihood."""
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            xx, yy = np.meshgrid(x, y)
            score = -0.5 * (((xx-config.area_width_m/2)/config.placeholder_width_m)**2
                            + ((yy-config.area_height_m/2)/config.placeholder_width_m)**2)
            weights = np.exp(score - score.max())
            return weights / weights.sum()
