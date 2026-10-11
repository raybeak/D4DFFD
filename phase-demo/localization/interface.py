"""Observation-only boundary: no experiment configuration or truth here."""
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, Sequence
import numpy as np
from config import EstimatorConfig
from models.observation import Observation
from models.receiver import Receiver


class Status(StrEnum):
    OK = "OK"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    STALE_DATA = "STALE_DATA"
    INVALID_INPUT = "INVALID_INPUT"
    ESTIMATOR_FAILURE = "ESTIMATOR_FAILURE"


@dataclass
class LocalizationResult:
    probability_grid: np.ndarray | None
    x_coordinates: np.ndarray
    y_coordinates: np.ndarray
    representative_position: tuple[float, float] | None
    status: Status
    active_observation_count: int
    timestamp: float
    emitter_id: str
    grid_resolution_m: float
    message: str = ""
    diagnostics: dict[str, int] = field(default_factory=dict)


class Estimator(Protocol):
    def estimate(self, observations: Sequence[Observation], receivers: Sequence[Receiver],
                 config: EstimatorConfig) -> LocalizationResult: ...


def validate_grid(grid: np.ndarray, x: np.ndarray, y: np.ndarray) -> None:
    """Reject invalid output; never repair or renormalize arbitrary results."""
    if x.ndim != 1 or y.ndim != 1 or not x.size or not y.size:
        raise ValueError("Coordinates must be nonempty 1D arrays")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("Nonfinite coordinates")
    if np.any(np.diff(x) <= 0) or np.any(np.diff(y) <= 0):
        raise ValueError("Coordinates must increase")
    if grid.shape != (y.size, x.size) or not np.isfinite(grid).all():
        raise ValueError("Invalid grid dimensions or nonfinite cells")
    if np.any(grid < 0) or not np.isclose(grid.sum(), 1.0, rtol=0, atol=1e-10):
        raise ValueError("Grid must be nonnegative and sum to one")
