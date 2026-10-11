"""Orchestration holds truth for evaluation; estimator receives only safe config."""
from dataclasses import asdict, replace
from pathlib import Path
from time import perf_counter
import json
import math
from config import ExperimentConfig
from simulation.synthetic import generate_observations
from models.emitter import Emitter
from models.ground_truth import GroundTruth
from localization.interface import Estimator
from localization.placeholder import PlaceholderEstimator
from evaluation.metrics import evaluate
from visualization.plot import plot_experiment

SCENARIOS = ("baseline", "noise", "dropout", "bias", "stale", "zero", "one", "disabled", "unknown_receiver", "wrong_emitter", "nan", "invalid_grid")


def scenario_config(base: ExperimentConfig, name: str) -> ExperimentConfig:
    if name not in SCENARIOS:
        raise ValueError("Unknown scenario")
    changes = {"noise": dict(observation_noise_level=2.0),
               "dropout": dict(observation_dropout_probability=0.5),
               "bias": dict(observation_bias=5.0),
               "stale": dict(measurement_timestamp=base.estimator.evaluation_timestamp-base.estimator.maximum_observation_age-1),
               "zero": dict(observation_dropout_probability=1.0),
               "disabled": dict(receivers=tuple(replace(r, enabled=False) for r in base.receivers))}
    return replace(base, **changes.get(name, {}))


def run_experiment(config: ExperimentConfig, scenario: str, output_dir: Path,
                   estimator: Estimator | None = None, make_plot: bool = True) -> dict:
    config = scenario_config(config, scenario)
    config.validate()
    emitter = Emitter(config.estimator.emitter_id)
    observations = generate_observations(config.receivers, emitter.emitter_id,
        seed=config.random_seed, timestamp=config.measurement_timestamp,
        noise=config.observation_noise_level, bias=config.observation_bias,
        dropout=config.observation_dropout_probability, base_value=config.synthetic_value)
    if scenario == "one":
        observations = observations[:1]
    if observations and scenario in ("unknown_receiver", "wrong_emitter", "nan"):
        change = {"unknown_receiver": {"receiver_id": "missing"},
                  "wrong_emitter": {"emitter_id": "other_emitter"}, "nan": {"value": float("nan")}}[scenario]
        observations = tuple(replace(o, **change) for o in observations)
    engine = estimator if estimator is not None else PlaceholderEstimator()
    if scenario == "invalid_grid" and estimator is None:
        class InvalidGridFixture(PlaceholderEstimator):
            def _fixture(self, x, y, config):
                return super()._fixture(x, y, config) * 0
        engine = InvalidGridFixture()
    start = perf_counter()
    result = engine.estimate(observations, config.receivers, config.estimator)
    elapsed = (perf_counter()-start)*1000
    # Construct truth only after estimation; it cannot influence the estimate.
    truth = GroundTruth(config.estimator.evaluation_timestamp, emitter.emitter_id,
                        config.test_emitter_x, config.test_emitter_y)
    metrics = evaluate(result, truth, config.thresholds, elapsed)
    metrics.update(scenario=scenario, random_seed=config.random_seed,
                   data_source="SYNTHETIC", estimator="PLACEHOLDER / NOT VALIDATED",
                   timing_scope="estimator call only; excludes plotting and I/O")
    destination = output_dir / scenario
    destination.mkdir(parents=True, exist_ok=True)
    # Strict JSON: intentionally invalid measurement NaN is represented by null + marker.
    rows = [asdict(o) for o in observations]
    for row in rows:
        if not math.isfinite(row["value"]):
            row["value"] = None
            row["invalid_value"] = "NaN"
    records = {"config.json": asdict(config), "observations.json": rows,
               "ground_truth.json": asdict(truth), "emitter.json": asdict(emitter),
               "metrics.json": metrics}
    for name, payload in records.items():
        (destination/name).write_text(json.dumps(payload, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    if make_plot:
        plot_experiment(result, config.receivers, truth, config.estimator, scenario, destination/"figure.png")
    return metrics
