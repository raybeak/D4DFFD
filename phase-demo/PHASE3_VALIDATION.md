# Phase 3 — actual validation report

Executed 2026-10-10, Python 3.12.14, NumPy 2.3.5, Matplotlib 3.10.8,
Pillow 12.3.0, Linux/Agg. Python 3.11 compatibility is by code/API requirements;
a separate 3.11 interpreter was not run.

## Results

| Check | Actual result |
| --- | --- |
| Before modifications | 83 tests in 1.703s, OK |
| Final complete suite | 112 tests in 4.638s, OK |
| Existing tests preserved | All 83 files/test methods remain unchanged and pass |
| New integration tests | 29 pass |
| NORMAL, UNCERTAIN, LOST CLI exports | All completed |
| PNG output | 63 per scenario, 189 total; all decoded/verified |
| GIF output | 3 GIFs, each with 63 decoded frames |
| Replay | CLI executed; 6 JSON/CSV logical-state/report files byte-identical |
| Legacy single experiment | Executed, output produced |
| Legacy 100-trial Monte Carlo | Executed, output produced |
| Legacy normal demo | Executed headlessly with frame export |
| Phase 2 telemetry CLI | Executed headlessly with mixed faults |
| Input preservation | All previous project files byte-identical except main.py and README.md |
| UI | Widgets and timer callbacks executed under Agg; selected exports visually inspected |

Raw suite logs are in `phase3_validation/`. Actual CLI stdout/stderr logs are
also retained there. There were no failing test runs during Phase 3 implementation.
The preserved-test row refers to test methods: the pre-existing test modules and
all their contents are byte-identical.

## Integration and integrity

The separate `integrated/` package owns the clock, pairing controller, dashboard,
replay manifests and exports. DemoPlayer and telemetry Engine are reused. Health
comes directly from Engine output; there is no replacement health state machine.
MockEstimator receives only an authored frame index for the visual fixture.
Telemetry values are never sent to either estimator. Evaluation code is unchanged.

Tests verify shared time, pause, reset, all three speeds, seek reconstruction,
scenario switching, engine-derived health, telemetry/map separation, no current
position during LOST, rendering, all export formats, invalid inputs, empty telemetry,
immutable raw messages, replay equality and preserved estimators.

SHA-256 matches the Phase 2 input:

- `localization/placeholder.py`: `f08cbd64318d01ad98c9e2e3675fe333825c8a0a252ec5ce2c90e25054cdbb3b`
- `demo/mock_estimator.py`: `9c919ea24e442a843548fc493542b4dfcbe719a91c5cc3ed4e71860753244fb0`

Both required disclaimers remain visible. The map clears current marker/blob/ring
when the authored position is null; recent history contains only past authored
points and breaks at missing frames. Pairing faults and map changes is not causal.

## Clock, pairing and replay

- NORMAL pairs authored normal with normal telemetry.
- UNCERTAIN pairs authored uncertain with mixed-fault telemetry.
- LOST pairs authored lost with outage/recovery telemetry.
- The common horizon is 30.75s. The map holds its final 30s frame for the final
  0.75s telemetry delivery deadline; its saturated local time is explicitly
  distinguished from the shared logical clock.
- All controls are in one window. Initial state/reset/scenario switch is paused;
  seek preserves current playback mode unless it reaches the end.
- The manifest embeds exact authored inputs and recorded telemetry. Replay loads
  saved time/speed/state; reset begins the full presentation again.
- Equality was confirmed for report.json, report.csv, messages.csv,
  telemetry_summary.csv, integrated_state.json and replay_manifest.json.

## Commands executed

From the project directory:

```bash
MPLBACKEND=Agg python -m unittest discover -s tests -v
python main.py --integrated normal --headless --save both --presentation --output-dir phase3_examples
python main.py --integrated uncertain --headless --save both --presentation --output-dir phase3_examples
python main.py --integrated lost --headless --save both --presentation --output-dir phase3_examples
python main.py --integrated-replay phase3_examples/integrated/normal/replay_manifest.json --headless --save frames --output-dir /workspace/scratch/72548d9de314/phase3_checks/replay
python main.py --output-dir /workspace/scratch/72548d9de314/phase3_checks/baseline
python main.py --monte-carlo 100 --output-dir /workspace/scratch/72548d9de314/phase3_checks/monte_carlo
python main.py --demo normal --headless --save frames --output-dir /workspace/scratch/72548d9de314/phase3_checks/demo
python -m telemetry --scenario telemetry/scenarios/mixed_faults.json --headless --output-dir /workspace/scratch/72548d9de314/phase3_checks/telemetry
```

Absolute output paths above record this run. On another computer use a writable
local output directory. README contains portable interactive/export commands.

## Delivered examples

`phase3_examples/integrated/{normal,uncertain,lost}/` contains each complete export:
63 PNGs, animation.gif, replay manifest, integrated state, telemetry CSV/JSON,
message CSV and frame timing metadata. `phase3_preview/` contains selected PNGs.
A GIF lasts 31.25 seconds at 1x: 30.75 seconds of timeline and a final 0.5-second
hold. Export sampling is 2 fps logical time plus the exact terminal time. Current
map positions are always selected from authored frames, never interpolated.

## Known limitations

- Native GUI windows were not manually operated. Automated widget/timer tests and
  headless rendering were actually executed; no desktop backend claim is made.
- Seek replays from the beginning. Entire recordings and GIF frames are in memory;
  this is a finite presentation application, not a scalable live hardware service.
- GIF timing is quantized to 10ms. Logical state is deterministic; image bytes may
  differ across fonts/backends/dependency versions.
- Missing Pillow is tested with an injected import failure. Matplotlib is installed
  in this environment, so a physically uninstalled Matplotlib environment was not run.
- Existing Phase 1.5 source-fingerprinted manifests require their original release;
  the integrity checks are preserved.
- Only Phase 3 presentation integration was added. No RF, location inference,
  target tracking, fusion, hardware acquisition or weapon interface was added.
