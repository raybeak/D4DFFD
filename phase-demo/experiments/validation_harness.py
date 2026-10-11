"""Phase 1.5: repeat the existing pipeline without adding an estimator."""
from dataclasses import asdict, replace
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Callable
import csv
import hashlib
import json
import platform

from config import ExperimentConfig, EstimatorConfig, EvaluationThresholds
from models.receiver import Receiver
from experiments.baseline import run_experiment, scenario_config, SCENARIOS
from evaluation.aggregation import (TRIAL_FIELDS, SUMMARY_FIELDS, OVERCONFIDENT_FIELDS,
    CALIBRATION_LABEL, STATUSES, trial_row, validate_trial, summarize, collect_overconfident)
from visualization.validation_plots import create_validation_plots

SOFTWARE_VERSION = "1.5.0"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def source_hashes() -> dict[str, str]:
    return {p.relative_to(PROJECT_ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(PROJECT_ROOT.rglob("*.py"))
            if not any(part.startswith(".") for part in p.relative_to(PROJECT_ROOT).parts)
            and "__pycache__" not in p.parts}


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_reports(rows: list[dict], scenarios: tuple[str, ...], output_dir: Path) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries = [summarize(rows, s) for s in scenarios]
    write_csv(output_dir/"trials.csv", TRIAL_FIELDS, rows)
    write_csv(output_dir/"summary.csv", SUMMARY_FIELDS, summaries)
    write_csv(output_dir/"overconfident_failures.csv", OVERCONFIDENT_FIELDS, collect_overconfident(rows))
    taxonomy = [dict(scenario=s["scenario"], status=status, count=s[f"status_{status}_count"],
                     percentage=s[f"status_{status}_pct"]) for s in summaries for status in STATUSES]
    write_csv(output_dir/"failure_taxonomy.csv", ("scenario", "status", "count", "percentage"), taxonomy)
    create_validation_plots(rows, summaries, output_dir)
    return summaries


def run_batch(config: ExperimentConfig, scenarios: tuple[str, ...], seed_start: int,
              number_of_trials: int, output_dir: Path,
              trial_executor: Callable = run_experiment) -> tuple[list[dict], list[dict]]:
    """Exceptions are recorded per trial; interrupt/system-exit still stop execution."""
    if type(number_of_trials) is not int or number_of_trials < 0 or type(seed_start) is not int or seed_start < 0:
        raise ValueError("Trial count and seed start must be nonnegative integers")
    if len(scenarios) != len(set(scenarios)) or any(s not in SCENARIOS for s in scenarios):
        raise ValueError("Scenarios must be known and unique")
    config.validate()
    output_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    rows = []
    for scenario in scenarios:
        for index in range(number_of_trials):
            seed = seed_start+index
            try:
                metrics = trial_executor(replace(config, random_seed=seed), scenario,
                    output_dir/"trial_artifacts"/scenario/f"{index:06d}", make_plot=False)
                row = trial_row(index, seed, scenario, metrics)
            except Exception as exc:
                row = dict.fromkeys(TRIAL_FIELDS)
                row.update(trial_id=index, seed=seed, scenario=scenario, status="ESTIMATOR_FAILURE",
                           failure_reason=str(exc), exception_type=type(exc).__name__)
            rows.append(row)
    summaries = write_reports(rows, scenarios, output_dir)
    manifest = {
        "schema_version": 1, "timestamp_utc": started,
        "software_version": SOFTWARE_VERSION, "source_sha256": source_hashes(),
        "scenarios": list(scenarios), "number_of_trials_per_scenario": number_of_trials,
        "total_trial_count": len(rows), "seed_start": seed_start,
        "seed_end_inclusive": seed_start+number_of_trials-1 if number_of_trials else None,
        "configuration": asdict(config),
        "effective_scenario_configurations": {s: asdict(scenario_config(config, s)) for s in scenarios},
        "configuration_note": "random_seed is overridden by seed_start + trial_id for every trial",
        "python_version": platform.python_version(), "platform": platform.platform(),
        "dependency_versions": {name: version(name) for name in ("numpy", "matplotlib")},
        "trial_executor": f"{trial_executor.__module__}.{trial_executor.__qualname__}",
        "calibration_status": CALIBRATION_LABEL, "data_source": "SYNTHETIC",
        "reproducibility_exclusions": ["processing_time_ms", "processing_time_median_ms",
                                        "processing_time_p90_ms", "timestamp_utc"],
        "standard_deviation": "population (ddof=0)", "percentiles": "NumPy linear interpolation",
        "coverage_denominator": "OK trials only; failure counts are reported separately",
        "timing_scope": "existing estimator call only; failed/exception timings are not in timing summaries",
        "artifact_note": "Only CSV rows define this batch; older trial_artifacts may remain after a shorter rerun",
    }
    (output_dir/"experiment_manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    return rows, summaries


def read_trials(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(TRIAL_FIELDS):
            raise ValueError("Unexpected trials.csv schema")
        rows = list(reader)
    for row in rows:
        for key in TRIAL_FIELDS:
            if row[key] == "" and key not in ("failure_reason", "exception_type"):
                row[key] = None
        for key in ("trial_id", "seed", "active_observation_count"):
            if row[key] is not None:
                row[key] = int(row[key])
        for key in ("position_error_m", "region_50_area_m2", "region_90_area_m2", "processing_time_ms"):
            if row[key] is not None:
                row[key] = float(row[key])
        for key in ("inside_50", "inside_90", "overconfident_failure"):
            if row[key] is not None:
                if row[key] not in ("True", "False"):
                    raise ValueError("Invalid CSV boolean")
                row[key] = row[key] == "True"
        validate_trial(row)
    return rows


def regenerate_reports(output_dir: Path) -> list[dict]:
    """Read saved trial rows; never rerun the estimator or replace the manifest."""
    manifest = json.loads((output_dir/"experiment_manifest.json").read_text(encoding="utf-8"))
    rows = read_trials(output_dir/"trials.csv")
    if len(rows) != manifest["total_trial_count"]:
        raise ValueError("Manifest/trial count mismatch")
    expected = {(s, i, manifest["seed_start"]+i) for s in manifest["scenarios"]
                for i in range(manifest["number_of_trials_per_scenario"])}
    actual = [(r["scenario"], r["trial_id"], r["seed"]) for r in rows]
    if len(set(actual)) != len(actual) or set(actual) != expected:
        raise ValueError("Manifest/trial identity mismatch")
    return write_reports(rows, tuple(manifest["scenarios"]), output_dir)


def config_from_manifest(manifest: dict) -> ExperimentConfig:
    raw = dict(manifest["configuration"])
    raw["estimator"] = EstimatorConfig(**raw["estimator"])
    raw["thresholds"] = EvaluationThresholds(**raw["thresholds"])
    raw["receivers"] = tuple(Receiver(**r) for r in raw["receivers"])
    return ExperimentConfig(**raw)


def replay_manifest(path: Path, output_dir: Path) -> tuple[list[dict], list[dict]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest["source_sha256"] != source_hashes():
        raise ValueError("Source differs from saved manifest; restore the recorded software before exact replay")
    expected_executor = f"{run_experiment.__module__}.{run_experiment.__qualname__}"
    if manifest["trial_executor"] != expected_executor:
        raise ValueError("Custom trial executors must be replayed by their owning code")
    if manifest["python_version"] != platform.python_version() or any(version(n) != v for n, v in manifest["dependency_versions"].items()):
        raise ValueError("Python/dependency versions differ from the manifest")
    return run_batch(config_from_manifest(manifest), tuple(manifest["scenarios"]),
                     manifest["seed_start"], manifest["number_of_trials_per_scenario"], output_dir)
