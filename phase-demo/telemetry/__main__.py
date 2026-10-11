"""Run with python -m telemetry; no imports from earlier project phases."""
import argparse
import json
import math
from pathlib import Path
from .engine import Engine, generate, load_recording, save_recording


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument('--scenario', type=Path)
    inputs.add_argument('--replay', type=Path)
    parser.add_argument('--seed', type=int)
    parser.add_argument('--output-dir', type=Path, default=Path('telemetry_output'))
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--speed', type=float, default=1.)
    args = parser.parse_args()
    try:
        if not math.isfinite(args.speed) or args.speed <= 0:
            raise ValueError('speed must be positive and finite')
        if args.replay:
            if args.seed is not None:
                raise ValueError('--seed cannot change recorded replay')
            recording = load_recording(args.replay)
        else:
            path = args.scenario or Path(__file__).parent / 'scenarios' / 'normal.json'
            config = json.loads(path.read_text(encoding='utf-8'))
            if args.seed is not None:
                config['seed'] = args.seed
            recording = generate(config)
        if args.headless:
            import matplotlib
            matplotlib.use('Agg')
        from .dashboard import Dashboard
        dashboard = Dashboard(recording)
        if args.headless:
            dashboard.update(recording['end_time'])
        else:
            dashboard.run(args.speed)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        dashboard.save(args.output_dir / 'dashboard.png')
        # Full reports are deterministic even if the user closes playback early.
        engine = Engine(recording)
        engine.advance(recording['end_time'])
        engine.export(args.output_dir)
        save_recording(recording, args.output_dir / 'recording.json')
        print(json.dumps(engine.snapshot(), indent=2, allow_nan=False))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
