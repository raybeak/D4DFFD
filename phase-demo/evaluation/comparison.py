"""Descriptive BASELINE/CANDIDATE differences; never rank estimators."""
import csv
import math
from pathlib import Path

COMPARE_METRICS = ("position_error_median_m", "position_error_p90_m", "coverage_50_pct",
                   "coverage_90_pct", "region_50_area_median_m2", "region_90_area_median_m2",
                   "processing_time_median_ms", "failure_rate_pct")
COMPARISON_FIELDS = ("scenario", "metric", "unit", "baseline", "candidate",
                     "candidate_minus_baseline", "comparison_status", "interpretation")


def load_summary(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if not set(("scenario", *COMPARE_METRICS)).issubset(reader.fieldnames or []):
            raise ValueError("Missing summary comparison columns")
        rows = list(reader)
    result = {}
    for row in rows:
        if not row["scenario"] or row["scenario"] in result:
            raise ValueError("Missing/duplicate scenario")
        result[row["scenario"]] = row
    return result


def compare_summaries(baseline: Path, candidate: Path, output: Path) -> list[dict]:
    a, b = load_summary(baseline), load_summary(candidate)
    rows = []
    for scenario in sorted(set(a) | set(b)):
        for metric in COMPARE_METRICS:
            left = a.get(scenario, {}).get(metric)
            right = b.get(scenario, {}).get(metric)
            left = float(left) if left not in ("", None) else None
            right = float(right) if right not in ("", None) else None
            if any(v is not None and not math.isfinite(v) for v in (left, right)):
                raise ValueError("Nonfinite saved summary")
            unit = "percentage_points" if metric.endswith("_pct") else "ms" if metric.endswith("_ms") else "m2" if metric.endswith("_m2") else "m"
            status = "COMPARABLE_VALUES" if left is not None and right is not None else "MISSING_VALUE_OR_SCENARIO"
            rows.append(dict(scenario=scenario, metric=metric, unit=unit, baseline=left, candidate=right,
                             candidate_minus_baseline=right-left if status == "COMPARABLE_VALUES" else None,
                             comparison_status=status,
                             interpretation="Descriptive only; setup equivalence and statistical significance not established"))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COMPARISON_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return rows
