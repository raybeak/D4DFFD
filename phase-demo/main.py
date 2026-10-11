"""Phase 1/1.5 commands and a separate predefined visualization demo."""
import argparse
from dataclasses import replace
from pathlib import Path
import json
from config import ExperimentConfig


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="baseline")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--monte-carlo", type=int, metavar="TRIALS")
    modes.add_argument("--report", action="store_true")
    modes.add_argument("--compare", nargs=2, type=Path, metavar=("BASELINE", "CANDIDATE"))
    modes.add_argument("--replay", type=Path, metavar="MANIFEST")
    modes.add_argument("--demo", choices=("normal", "uncertain", "lost"))
    modes.add_argument("--integrated", choices=("normal", "uncertain", "lost"))
    modes.add_argument("--integrated-replay", type=Path, metavar="MANIFEST")
    parser.add_argument("--speed", type=float, choices=(.5, 1., 2.), default=1.)
    parser.add_argument("--presentation", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--save", choices=("gif", "frames", "both"))
    parser.add_argument("--seed-start", type=int, default=None)
    args = parser.parse_args()
    if args.integrated or args.integrated_replay:
        try:
            from integrated.dashboard import run_integrated
            output = run_integrated(args.integrated, args.speed, args.presentation, args.headless,
                                    args.save, args.output_dir, args.seed, args.integrated_replay)
        except (ValueError, OSError, ImportError) as exc:
            parser.error(f"Integrated dashboard: {exc}")
        print(f"SYNTHETIC DEMONSTRATION | output (if saved): {output}")
        return
    if args.demo:
        from demo.dashboard import run_demo
        try:
            output = run_demo(args.demo, args.speed, args.presentation, args.headless, args.save, args.output_dir)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        print(f"SIMULATED / PREDEFINED DATA | demo={args.demo} | export directory (if saved): {output}")
        return
    if args.presentation or args.headless or args.save or args.speed != 1.:
        parser.error("--speed/--presentation/--headless/--save require --demo, --integrated or --integrated-replay")
    # Lazy imports prevent the Phase 1 Agg backend from disabling interactive demo windows.
    from experiments.baseline import SCENARIOS, run_experiment
    from experiments.validation_harness import run_batch, regenerate_reports, replay_manifest
    from evaluation.comparison import compare_summaries
    if args.scenario not in (*SCENARIOS, "all"):
        parser.error("Unknown scenario; choose " + ", ".join((*SCENARIOS, "all")))
    config = replace(ExperimentConfig(), random_seed=args.seed)
    scenarios = SCENARIOS if args.scenario == "all" else (args.scenario,)
    try:
        if args.compare:
            rows = compare_summaries(*args.compare, args.output_dir/"regression_comparison.csv")
            print(json.dumps(rows, indent=2, allow_nan=False))
            return
        if args.report:
            summaries = regenerate_reports(args.output_dir)
        elif args.replay:
            _, summaries = replay_manifest(args.replay, args.output_dir)
        elif args.monte_carlo is not None:
            _, summaries = run_batch(config, scenarios,
                args.seed if args.seed_start is None else args.seed_start,
                args.monte_carlo, args.output_dir)
        else:
            summaries = None
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    if summaries is not None:
        print(json.dumps(summaries, indent=2, allow_nan=False))
        return
    for scenario in scenarios:
        metrics = run_experiment(config, scenario, args.output_dir)
        print(json.dumps(metrics, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
