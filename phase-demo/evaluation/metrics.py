"""Generic distribution diagnostics; model mass is NOT calibrated confidence."""
from dataclasses import dataclass
import math
import numpy as np
from config import EvaluationThresholds
from models.ground_truth import GroundTruth
from localization.interface import LocalizationResult, Status, validate_grid


@dataclass
class ModelRegion:
    mask: np.ndarray
    cell_count: int
    area_m2: float
    actual_mass: float


def model_region(grid: np.ndarray, mass: float, cell_area_m2: float) -> ModelRegion:
    """Highest-cell-mass region. Include all cutoff ties to avoid arbitrary shapes."""
    if grid.ndim != 2 or not 0 < mass <= 1 or not math.isfinite(cell_area_m2) or cell_area_m2 <= 0:
        raise ValueError("Invalid region parameters")
    validate_grid(grid, np.arange(grid.shape[1]), np.arange(grid.shape[0]))
    descending = np.sort(grid.ravel())[::-1]
    # Summing decimal masses can yield 0.8999999999999999 for 0.9.
    tolerance = 8 * np.finfo(float).eps
    index = min(int(np.searchsorted(np.cumsum(descending), mass-tolerance, side="left")), descending.size-1)
    mask = grid >= descending[index]
    count = int(mask.sum())
    return ModelRegion(mask, count, count*cell_area_m2, float(grid[mask].sum()))


def contains(region: ModelRegion, result: LocalizationResult, truth: GroundTruth) -> bool:
    """Cell footprints are left-closed; the outer maximum boundary is included."""
    step = result.grid_resolution_m
    xmin, ymin = result.x_coordinates[0]-step/2, result.y_coordinates[0]-step/2
    xmax, ymax = result.x_coordinates[-1]+step/2, result.y_coordinates[-1]+step/2
    if not (xmin <= truth.x <= xmax and ymin <= truth.y <= ymax):
        return False
    ix = min(int((truth.x-xmin)//step), len(result.x_coordinates)-1)
    iy = min(int((truth.y-ymin)//step), len(result.y_coordinates)-1)
    return bool(region.mask[iy, ix])


def evaluate(result: LocalizationResult, truth: GroundTruth,
             thresholds: EvaluationThresholds, processing_time_ms: float) -> dict:
    if result.emitter_id != truth.emitter_id or result.timestamp != truth.timestamp:
        raise ValueError("Evaluation requires matching emitter and timestamp")
    if not all(math.isfinite(v) for v in (truth.x, truth.y, processing_time_ms,
            thresholds.large_error_threshold_m, thresholds.small_uncertainty_area_threshold_m2)):
        raise ValueError("Nonfinite evaluation input")
    if min(processing_time_ms, thresholds.large_error_threshold_m, thresholds.small_uncertainty_area_threshold_m2) < 0:
        raise ValueError("Negative time or threshold")
    metrics = dict(status=result.status.value, representative_position=result.representative_position,
                   ground_truth=[truth.x, truth.y], position_error_m=None,
                   ground_truth_inside_50_region=None, ground_truth_inside_90_region=None,
                   region_50_area_m2=None, region_90_area_m2=None,
                   region_50_actual_mass=None, region_90_actual_mass=None,
                   processing_time_ms=processing_time_ms,
                   active_observation_count=result.active_observation_count,
                   overconfident_failure=None, message=result.message,
                   diagnostics=result.diagnostics)
    if result.status != Status.OK:
        return metrics
    if result.probability_grid is None or result.representative_position is None:
        metrics.update(status=Status.ESTIMATOR_FAILURE.value, message="Missing estimator output")
        return metrics
    try:
        validate_grid(result.probability_grid, result.x_coordinates, result.y_coordinates)
        if not all(math.isfinite(v) for v in result.representative_position):
            raise ValueError("Invalid representative position")
        regions = [model_region(result.probability_grid, p, result.grid_resolution_m**2) for p in (0.5, 0.9)]
    except ValueError as exc:
        metrics.update(status=Status.ESTIMATOR_FAILURE.value, message=str(exc))
        return metrics
    error = math.hypot(result.representative_position[0]-truth.x, result.representative_position[1]-truth.y)
    metrics["position_error_m"] = error
    for label, region in zip((50, 90), regions):
        metrics[f"region_{label}_area_m2"] = region.area_m2
        metrics[f"region_{label}_actual_mass"] = region.actual_mass
        metrics[f"ground_truth_inside_{label}_region"] = contains(region, result, truth)
    metrics["overconfident_failure"] = bool(error > thresholds.large_error_threshold_m and regions[1].area_m2 < thresholds.small_uncertainty_area_threshold_m2)
    return metrics
