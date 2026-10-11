"""Separate descriptive plots for synthetic validation batches."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def create_validation_plots(rows: list[dict], summaries: list[dict], output: Path) -> None:
    names = [s["scenario"] for s in summaries]
    valid = [r for r in rows if r["status"] == "OK"]
    failed = len(rows)-len(valid)
    # Separate image files, with empty/all-failed batches explicitly represented.
    for filename, fields, ylabel in (
        ("position_error_distribution.png", ("position_error_m",), "Position error (m)"),
        ("uncertainty_area_distribution.png", ("region_50_area_m2", "region_90_area_m2"), "Model-region area (m²)"),
        ("processing_time_distribution.png", ("processing_time_ms",), "Estimator-call time (ms)"),
    ):
        fig, ax = plt.subplots(figsize=(max(8, len(names)*1.1), 5), layout="constrained")
        data, labels = [], []
        for name in names:
            for field in fields:
                values = [r[field] for r in valid if r["scenario"] == name]
                if values:
                    data.append(values)
                    labels.append(name + (" / 50%" if "50" in field else " / 90%" if "90" in field else ""))
        if data:
            ax.boxplot(data, whis=(0, 100), showfliers=False)
            ax.set_xticks(range(1, len(labels)+1), labels, rotation=35, ha="right")
        else:
            ax.text(.5, .5, "NO VALID TRIALS", transform=ax.transAxes, ha="center")
            ax.set_xticks([])
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=.2)
        ax.set_title(f"SYNTHETIC EXPERIMENT — placeholder validation\nValid: {len(valid)} | Failed: {failed} | Boxes: quartiles, whiskers: min/max", fontsize=10)
        fig.savefig(output/filename, dpi=140)
        plt.close(fig)
    fig, ax = plt.subplots(figsize=(max(8, len(names)*.9), 5), layout="constrained")
    positions = np.arange(len(names))
    for offset, mass, color in ((-.18, 50, "#1976b9"), (.18, 90, "#dc7a28")):
        heights = [s[f"coverage_{mass}_pct"] if s[f"coverage_{mass}_pct"] is not None else np.nan for s in summaries]
        ax.bar(positions+offset, heights, width=.34, label=f"Observed inclusion / {mass}% model region", color=color)
        ax.axhline(mass, color=color, linestyle="--", alpha=.7, label=f"Nominal {mass}% mass")
        for pos, height in zip(positions+offset, heights):
            if np.isfinite(height):
                ax.text(pos, height+2, f"{height:.1f}", ha="center", fontsize=8)
    for pos, summary in zip(positions, summaries):
        if summary["valid_trial_count"] == 0:
            ax.text(pos, 5, "N/A", ha="center")
    if not summaries:
        ax.text(.5, .3, "EMPTY EXPERIMENT", transform=ax.transAxes, ha="center")
    ax.set_xticks(positions, [f"{s['scenario']}\nvalid n={s['valid_trial_count']}" for s in summaries], rotation=30, ha="right")
    ax.set_ylim(0, 115)
    ax.set_ylabel("Inclusion among valid trials (%)")
    ax.set_title(f"SYNTHETIC EXPERIMENT — coverage comparison\nCALIBRATION NOT ESTABLISHED | Failed trials: {failed}", fontsize=10)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8)
    fig.savefig(output/"coverage_comparison.png", dpi=140)
    plt.close(fig)
