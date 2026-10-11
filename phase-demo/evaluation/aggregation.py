"""Strict trial contracts and descriptive statistics; no calibration claims."""
from collections import Counter
import math
import numpy as np

STATUSES = ("OK", "INSUFFICIENT_DATA", "STALE_DATA", "INVALID_INPUT", "ESTIMATOR_FAILURE")
CALIBRATION_LABEL = "CALIBRATION NOT ESTABLISHED"
TRIAL_FIELDS = (
    "trial_id", "seed", "scenario", "status", "position_error_m",
    "region_50_area_m2", "region_90_area_m2", "inside_50", "inside_90",
    "processing_time_ms", "active_observation_count", "overconfident_failure",
    "failure_reason", "exception_type",
)
OVERCONFIDENT_FIELDS = ("scenario", "trial_id", "seed", "position_error_m",
                        "region_90_area_m2", "status")
SUMMARY_FIELDS = (
    "scenario", "total_trial_count", "valid_trial_count", "failed_trial_count",
    "failure_rate_pct", "position_error_mean_m", "position_error_median_m",
    "position_error_std_m", "position_error_p90_m", "position_error_p95_m",
    "position_error_max_m", "region_50_area_median_m2", "region_90_area_median_m2",
    "nominal_50_mass_pct", "coverage_50_pct", "nominal_90_mass_pct", "coverage_90_pct",
    "processing_time_median_ms", "processing_time_p90_ms", "overconfident_failure_count",
    "calibration_status",
) + tuple(f"status_{s}_{suffix}" for s in STATUSES for suffix in ("count", "pct"))


def trial_row(trial_id: int, seed: int, scenario: str, metrics: dict) -> dict:
    """Validate returned metrics before admitting a trial to summary statistics."""
    row = {field: None for field in TRIAL_FIELDS}
    row.update(trial_id=trial_id, seed=seed, scenario=scenario, status=metrics["status"],
               failure_reason="", exception_type="")
    if row["status"] not in STATUSES:
        raise ValueError("Unknown trial status")
    for key in ("position_error_m", "region_50_area_m2", "region_90_area_m2",
                "processing_time_ms", "active_observation_count", "overconfident_failure"):
        row[key] = metrics.get(key)
    row["inside_50"] = metrics.get("ground_truth_inside_50_region")
    row["inside_90"] = metrics.get("ground_truth_inside_90_region")
    if row["status"] != "OK":
        row["failure_reason"] = str(metrics.get("message", "Trial failed"))
        for key in ("position_error_m", "region_50_area_m2", "region_90_area_m2",
                    "inside_50", "inside_90", "overconfident_failure"):
            row[key] = None
    validate_trial(row)
    return row


def validate_trial(row: dict) -> None:
    if row["status"] not in STATUSES or not row["scenario"]:
        raise ValueError("Invalid scenario or status")
    for key in ("trial_id", "seed"):
        if type(row[key]) is not int or row[key] < 0:
            raise ValueError(f"Invalid {key}")
    count = row["active_observation_count"]
    if count is not None and (type(count) is not int or count < 0):
        raise ValueError("Invalid active observation count")
    for key in ("position_error_m", "region_50_area_m2", "region_90_area_m2", "processing_time_ms"):
        value = row[key]
        if value is not None and (type(value) not in (float, int) or not math.isfinite(value) or value < 0):
            raise ValueError(f"Invalid {key}")
        if row["status"] == "OK" and value is None:
            raise ValueError(f"Missing {key} on OK trial")
    for key in ("inside_50", "inside_90", "overconfident_failure"):
        if row[key] is not None and type(row[key]) is not bool:
            raise ValueError(f"Invalid boolean {key}")
        if row["status"] == "OK" and row[key] is None:
            raise ValueError(f"Missing {key}")
    if row["status"] == "OK":
        if count is None or row["region_50_area_m2"] > row["region_90_area_m2"]:
            raise ValueError("Invalid OK count or non-nested region areas")
        if row["inside_50"] and not row["inside_90"]:
            raise ValueError("Inconsistent nested-region inclusion")
    elif any(row[k] is not None for k in ("position_error_m", "region_50_area_m2", "region_90_area_m2",
                                          "inside_50", "inside_90", "overconfident_failure")):
        raise ValueError("Failed trials cannot contain scored results")


def summarize(rows: list[dict], scenario: str) -> dict:
    selected = [r for r in rows if r["scenario"] == scenario]
    for row in selected:
        validate_trial(row)
    identities = [(r["trial_id"], r["seed"]) for r in selected]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate trial identity")
    valid = [r for r in selected if r["status"] == "OK"]
    total, count = len(selected), len(valid)
    result = dict.fromkeys(SUMMARY_FIELDS)
    result.update(scenario=scenario, total_trial_count=total, valid_trial_count=count,
                  failed_trial_count=total-count, failure_rate_pct=100*(total-count)/total if total else None,
                  nominal_50_mass_pct=50.0, nominal_90_mass_pct=90.0,
                  overconfident_failure_count=sum(r["overconfident_failure"] is True for r in valid),
                  calibration_status=CALIBRATION_LABEL)
    counts = Counter(r["status"] for r in selected)
    for status in STATUSES:
        result[f"status_{status}_count"] = counts[status]
        result[f"status_{status}_pct"] = 100*counts[status]/total if total else None
    if not valid:
        return result
    errors = np.array([r["position_error_m"] for r in valid])
    for label, value in (("mean", np.mean(errors)), ("median", np.median(errors)),
                         ("std", np.std(errors, ddof=0)), ("p90", np.percentile(errors, 90)),
                         ("p95", np.percentile(errors, 95)), ("max", np.max(errors))):
        result[f"position_error_{label}_m"] = float(value)
    for mass in (50, 90):
        result[f"region_{mass}_area_median_m2"] = float(np.median([r[f"region_{mass}_area_m2"] for r in valid]))
        result[f"coverage_{mass}_pct"] = 100*sum(r[f"inside_{mass}"] for r in valid)/count
    times = [r["processing_time_ms"] for r in valid]
    result["processing_time_median_ms"] = float(np.median(times))
    result["processing_time_p90_ms"] = float(np.percentile(times, 90))
    return result


def collect_overconfident(rows: list[dict]) -> list[dict]:
    return [{k: row[k] for k in OVERCONFIDENT_FIELDS} for row in rows
            if row["status"] == "OK" and row["overconfident_failure"] is True]
