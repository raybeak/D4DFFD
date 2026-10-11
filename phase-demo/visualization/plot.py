"""Evaluation-only figures. Always show synthetic and placeholder labels."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from config import EstimatorConfig
from evaluation.metrics import model_region
from localization.interface import LocalizationResult, Status
from models.ground_truth import GroundTruth
from models.receiver import Receiver


def plot_experiment(result: LocalizationResult, receivers: tuple[Receiver, ...],
                    truth: GroundTruth, config: EstimatorConfig,
                    scenario: str, output: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.4, 7.4), layout="constrained")
    if result.status == Status.OK and result.probability_grid is not None:
        image = ax.imshow(result.probability_grid, origin="lower",
                          extent=(0, config.area_width_m, 0, config.area_height_m), cmap="viridis")
        fig.colorbar(image, ax=ax, label="Placeholder normalized cell mass")
        for mass, color, style in ((0.9, "white", "--"), (0.5, "cyan", "-")):
            region = model_region(result.probability_grid, mass, config.grid_resolution_m**2)
            if region.mask.any() and not region.mask.all():
                ax.contour(result.x_coordinates, result.y_coordinates, region.mask.astype(float),
                           levels=[0.5], colors=[color], linestyles=[style])
            ax.plot([], [], color=color, linestyle=style, label=f"{mass:.0%} model region (uncalibrated)")
        ax.scatter(*result.representative_position, marker="X", s=120, c="orange", edgecolors="black", label="ESTIMATE (fixed placeholder)", zorder=5)
    else:
        ax.text(0.5, 0.5, f"{result.status.value}\nNo spatial result", ha="center", va="center", transform=ax.transAxes)
    for enabled, marker, label in ((True, "^", "Receiver"), (False, "v", "Disabled receiver")):
        nodes = [r for r in receivers if r.enabled == enabled]
        if nodes:
            ax.scatter([r.x for r in nodes], [r.y for r in nodes], marker=marker, c="lightgray", edgecolors="black", s=75, label=label)
    ax.scatter(truth.x, truth.y, marker="*", c="magenta", edgecolors="black", s=210, label="GROUND TRUTH (synthetic)", zorder=6)
    ax.set(xlim=(0, config.area_width_m), ylim=(0, config.area_height_m), xlabel="x / East (m)", ylabel="y / North (m)")
    ax.set_aspect("equal")
    ax.set_title(f"SYNTHETIC EXPERIMENT | {scenario}\nPLACEHOLDER / NOT VALIDATED / No RF localization", fontsize=11)
    ax.legend(loc="upper center", fontsize=8, facecolor="#444444", labelcolor="white")
    fig.savefig(output, dpi=150)
    plt.close(fig)
