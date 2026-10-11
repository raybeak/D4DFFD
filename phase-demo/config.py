"""Experiment settings; only EstimatorConfig crosses the estimator boundary."""
from dataclasses import dataclass
import math
from models.receiver import Receiver


@dataclass(frozen=True)
class EstimatorConfig:
    area_width_m: float = 100.0
    area_height_m: float = 100.0
    grid_resolution_m: float = 2.0
    emitter_id: str = "test_emitter"
    evaluation_timestamp: float = 100.0
    maximum_observation_age: float = 5.0
    placeholder_width_m: float = 10.0

    def validate(self) -> None:
        for value in (self.area_width_m, self.area_height_m,
                      self.grid_resolution_m, self.placeholder_width_m):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Spatial settings must be finite and positive")
        if not self.emitter_id or not math.isfinite(self.evaluation_timestamp):
            raise ValueError("Invalid emitter ID or evaluation time")
        if not math.isfinite(self.maximum_observation_age) or self.maximum_observation_age < 0:
            raise ValueError("Invalid maximum observation age")
        for length in (self.area_width_m, self.area_height_m):
            cells = length / self.grid_resolution_m
            if not math.isclose(cells, round(cells), abs_tol=1e-9) or cells < 1:
                raise ValueError("Area dimensions must be integer multiples of resolution")
        if self.area_width_m * self.area_height_m / self.grid_resolution_m**2 > 1_000_000:
            raise ValueError("Phase 1 grid limit: 1,000,000 cells")


@dataclass(frozen=True)
class EvaluationThresholds:
    large_error_threshold_m: float = 20.0
    small_uncertainty_area_threshold_m2: float = 1600.0


@dataclass(frozen=True)
class ExperimentConfig:
    random_seed: int = 42
    estimator: EstimatorConfig = EstimatorConfig()
    receivers: tuple[Receiver, ...] = (
        Receiver("r1", 10, 10), Receiver("r2", 90, 10),
        Receiver("r3", 90, 90), Receiver("r4", 10, 90),
    )
    test_emitter_x: float = 75.0
    test_emitter_y: float = 70.0
    observation_noise_level: float = 0.1
    observation_bias: float = 0.0
    observation_dropout_probability: float = 0.0
    measurement_timestamp: float = 100.0
    synthetic_value: float = 1.0
    thresholds: EvaluationThresholds = EvaluationThresholds()

    def validate(self) -> None:
        self.estimator.validate()
        if not isinstance(self.random_seed, int) or self.random_seed < 0:
            raise ValueError("Seed must be a nonnegative integer")
        values = (self.test_emitter_x, self.test_emitter_y,
                  self.observation_noise_level, self.observation_bias,
                  self.observation_dropout_probability, self.measurement_timestamp,
                  self.synthetic_value, self.thresholds.large_error_threshold_m,
                  self.thresholds.small_uncertainty_area_threshold_m2)
        if not all(math.isfinite(v) for v in values):
            raise ValueError("Nonfinite experiment setting")
        if self.observation_noise_level < 0 or not 0 <= self.observation_dropout_probability <= 1:
            raise ValueError("Invalid noise or dropout setting")
        if not 0 <= self.test_emitter_x <= self.estimator.area_width_m or not 0 <= self.test_emitter_y <= self.estimator.area_height_m:
            raise ValueError("Ground truth outside test area")
        if min(self.thresholds.large_error_threshold_m, self.thresholds.small_uncertainty_area_threshold_m2) < 0:
            raise ValueError("Evaluation thresholds must be nonnegative")
