# Predefined Visualization Demo + Phase 1 / 1.5

**The Demo Phase does not perform RF localization.
Positions and uncertainty are predefined for demonstration.**

Phase 1 provides the experiment pipeline. Phase 1.5 adds validation and repeated testing.
The Demo Phase is a separate replay/UI layer. It does not provide Phase 2 estimation or
any tracking algorithm. Every screen permanently states SIMULATED / PREDEFINED DATA.

## Run the demo

Python 3.11+ is required. Extract this archive and run:

```sh
cd phase-demo
python -m pip install -r requirements.txt
python main.py --demo normal
python main.py --demo uncertain
python main.py --demo lost
python main.py --demo normal --speed 2 --presentation
```

On a desktop with an available Matplotlib interactive backend, this opens a window and
starts playback. Click PLAY / PAUSE or RESET. Keyboard controls (focus the figure first):

| Control | Action |
|---|---|
| Space | Toggle play/pause |
| R | Reset to first frame and pause |
| 1 | 0.5x speed |
| 2 | 1x speed |
| 3 | 2x speed |

The demo stops at its final frame. Press Reset, then Play to start again. Presentation
mode enlarges the main heading; the default dashboard already uses a readable 16:9 layout.

Headless machines automatically save a GIF instead of opening a window. To export
explicitly on any machine:

```sh
python main.py --demo normal --headless --save both --presentation
python main.py --demo uncertain --headless --save gif
python main.py --demo lost --headless --save frames
```

Exports live under `outputs/demo/<name>/`: animation.gif, frame_000.png through
frame_030.png (depending on --save), and replay_manifest.json. No FFmpeg is required.
Pillow is an existing Matplotlib dependency; no new dependency was added. Without
--headless, --save exports first and then opens the interactive window if available.
An unavailable GUI backend does not imply the demo cannot run: use --headless.

GIFs loop automatically and have no interactive controls. Each authored frame is held
until the next JSON timestamp, scaled by --speed. The terminal frame holds for one extra
demo second. A 30-second scenario therefore produces a 31-second GIF at 1x. GIF durations
are rounded to 10 ms and constrained to at least 10 ms. No intermediate positions are
generated. Saved images use the REPLAY EXPORT playback label.

## Authored scenarios

Each scenario contains 31 explicit frames at timestamps 0 through 30 seconds.

| Scenario | Predefined behavior |
|---|---|
| NORMAL_TRACK | Path from (20,20) to (80,78); visual radius decreases from 24 m to 5 m; confidence labels LOW/MEDIUM/HIGH |
| UNCERTAIN_TRACK | Moving path from (22,32) to (82,33); radius remains 28 m; confidence stays LOW |
| LOST_TRACK | TRACKING at 0–7 s, DEGRADED at 8–9 s, LOST at 10–16 s, REACQUIRING at 17–18 s, TRACKING at 19–30 s |

Missing-position frames contain null position/radius and UNKNOWN confidence. The UI
removes the current marker and blob immediately. It retains at most the last 15 authored
frames of history, with line breaks through missing frames. There is no extrapolation,
gap filling, reacquisition algorithm, uncertainty inference, or future trajectory display.
Even the status transitions and confidence labels are directly authored in JSON.

## Demo module and JSON contract

- `demo/scenario.py`: immutable scenario/frame data and strict JSON validation.
- `demo/mock_estimator.py`: scenario/frame adapter returning LocalizationResult.
- `demo/player.py`: deterministic clock, speed, pause/reset, and bounded history.
- `demo/dashboard.py`: Matplotlib UI and PNG/GIF export.
- `demo/scenarios/{normal,uncertain,lost}.json`: explicit demo values.
- `tests/test_demo.py`: replay, display, isolation, and export checks.

The JSON root includes schema_version=1, data_source="SIMULATED / PREDEFINED DATA",
scenario_name, duration_seconds, area_width_m, area_height_m, grid_resolution_m, frames.
Each frame explicitly contains time, position, uncertainty_radius, confidence_label,
track_status. Times strictly increase; the first is zero and last equals duration.
Positions must lie inside the area. Unknown fields, invalid state labels, nonfinite values,
and inconsistent missing-position states are rejected.

MockEstimator uses the existing LocalizationResult data contract, but intentionally has
a frame-replay API: `MockEstimator(scenario).estimate(frame_index, observations=None)`.
Its optional observations argument is ignored. It never queries receivers or derives
position from measurements. representative_position is copied exactly from JSON and
need not coincide with a grid-cell center. It is not a MAP estimate.

The normalized blob is only a visual fixture. Its drawn ring is the predefined radius;
the bell-shaped display uses radius/2 as its visual sigma. This convention is not a
confidence level, calibration, or physical sensor model. The blob can be clipped by the
map boundary. `active_observation_count` is always zero; `OK` means a predefined position
is available, not a measurement-supported estimate. Missing scripted positions return
INSUFFICIENT_DATA and no grid; the separate UI label is DEGRADED or LOST as authored.
Demo results are not submitted to the Phase 1.5 accuracy benchmark.

## Compatibility and validation

PlaceholderEstimator, all Phase 1/1.5 computational modules, and all 42 original tests are
unchanged. Only main.py was modified among the original Python files, to add demo CLI
dispatch and lazy imports. Lazy imports keep the existing Phase 1 headless plotting
backend from preventing an interactive demo window. Existing commands remain available:

```sh
python main.py
python main.py --monte-carlo 100
python main.py --report
python -m unittest discover -s tests -v
```

The original Phase 1.5 output files are retained. Their manifests fingerprint the old
source release, so exact replay of those old manifests still requires the original
Phase 1.5 release. This check was not weakened. For a batch made with this demo release:

```sh
python main.py --monte-carlo 100 --output-dir demo_validation
python main.py --replay demo_validation/experiment_manifest.json --output-dir demo_replay
python main.py --compare demo_validation/summary.csv demo_replay/summary.csv --output-dir demo_comparison
```

Headless rendering and keyboard/button callback logic were tested in the build environment.
A native desktop window could not be manually exercised there. Playback uses a monotonic
clock; a slow GUI can skip displaying authored frames, but it never predicts positions.
PNG/GIF export includes all authored frames. Rendering bytes/fonts can differ across
platforms; scripted positions and replay states remain deterministic.

## Preserved Phase 1.5 documentation

Phase 1's estimator, data generator, evaluation pipeline, and 23 original tests remain
unchanged. Phase 1.5 adds repeated execution, validation of trial records, aggregation,
manifests, plots, and descriptive comparisons. **No new localization algorithm exists.**

## Phase 1.5 quick start

After extracting the ZIP:

```sh
cd phase-demo
python -m pip install -r requirements.txt
python main.py
python main.py --monte-carlo 100 --seed-start 42
python main.py --report
python -m unittest discover -s tests -v
```

`python main.py` retains Phase 1 behavior. The Monte Carlo command uses the baseline
scenario by default. Trial IDs are zero-based and seeds are 42 through 141 inclusive.
`--report` rebuilds tables and plots from saved trials without executing the estimator.

```sh
python main.py --scenario all --monte-carlo 5 --seed-start 42 --output-dir failure_demo
python main.py --replay outputs/experiment_manifest.json --output-dir replay_output
python main.py --compare outputs/summary.csv replay_output/summary.csv --output-dir comparison_output
```

Exact replay restores configuration and seeds from the manifest. It checks Python,
dependency versions, and all recorded Python source hashes before running. Retain the
source ZIP with the manifest. Custom injected trial executors require their own caller
for replay. Run `--replay` with a different output directory to retain the original batch.

## Monte Carlo and reporting semantics

Monte Carlo here means repeating the same scenario with a deterministic sequence of
different random seeds. It tests execution and descriptive reporting. The fixed placeholder
distribution cannot reveal measurement-dependent accuracy or robustness. Synthetic noise
changes observations, while the spatial fixture and baseline position metrics stay fixed.

Empirical coverage is the fraction of **valid (OK)** trials whose synthetic truth lies in
the respective model region. Example: 7 included out of 10 valid is 70%, even if another
2 trials failed. Both failures are reported; they are never removed from total counts or
failure-rate denominators. An empty or all-failed batch has blank/NA coverage, not 0%.

All reports state **CALIBRATION NOT ESTABLISHED**. Even many seeds at one fixed setup do
not establish general calibration, especially with this deliberately fixed placeholder.
An overconfident failure means large error AND small 90% model-region area according to
the existing fixed configuration thresholds. It is distinct from an execution failure:
an OK software trial can be an overconfident failure. Synthetic results are not hardware
performance, and these thresholds are not operational acceptance criteria.

Summary statistics use OK trials only: mean/median/population standard deviation (ddof=0),
linear-interpolated 90th/95th percentiles, and maximum error; median model-region areas;
coverage; median and 90th percentile estimator-call time. For a single trial std is 0;
for zero valid trials numeric statistics are blank. State counts and percentages use all
attempted trials. A truly empty batch has zero counts and undefined percentages.

An exception or malformed returned metric becomes ESTIMATOR_FAILURE with exception type
and reason. Subsequent trials continue. KeyboardInterrupt/SystemExit are not swallowed.
Exceptions have no invented timing/count/error metrics. Filesystem errors that prevent
the final reports from being saved still terminate with a visible error.

## Batch outputs

| File | Content |
|---|---|
| trials.csv | One row per attempted trial, including failures |
| summary.csv | One row per requested scenario; units in column names |
| overconfident_failures.csv | Every flagged valid trial |
| failure_taxonomy.csv | All five states, counts, percentages by scenario |
| experiment_manifest.json | UTC timestamp, version, source hashes, configuration, seed range, environment |
| position_error_distribution.png | Error boxplots by scenario |
| uncertainty_area_distribution.png | Separate 50%/90% area boxplots |
| processing_time_distribution.png | Estimator-call timing boxplots |
| coverage_comparison.png | Nominal model mass and empirical inclusion |
| trial_artifacts/ | Original per-trial inputs, truth, config, and metrics |

Boxplot whiskers are min/max, the box is the middle 50%, and the line is the median.
Degenerate boxes in the baseline are expected: this placeholder is fixed.
Plots identify valid/failed counts; empty/all-failed batches receive explicit labels.
The plotting backend is headless and creates files without opening a window.

Per-trial CSV booleans are True/False; unavailable values are empty fields. Coverage/rates
in summary CSV use percent, not fractions. Comparison rate deltas use percentage points.
`--compare` aligns scenarios by name and reports CANDIDATE minus BASELINE. Missing values
remain missing, not zero. It does not establish comparable experimental conditions,
statistical significance, or superiority of any estimator.

Reproducibility equality excludes wall-clock timing. Manifest creation timestamps also
differ between runs; they are metadata, not experiment outcomes. New runs overwrite named
reports. Older per-trial folders may remain after a shorter rerun; CSV rows and manifest
identify the current batch. Use distinct output directories to retain multiple batches.
Per-trial artifacts grow linearly with trials; there is no parallel execution or database.

The sections below describe the preserved Phase 1 pipeline.

**SYNTHETIC DATA / PLACEHOLDER / NOT VALIDATED / NOT A REAL RF LOCALIZATION ALGORITHM**

이 프로젝트는 데이터 생성 → 분석 인터페이스 → 시각화 → 평가의 연결을 검증합니다.
실제 전파 모델, RF 위치 추정, 이동 추적, 장비 연결은 구현하지 않았습니다.

## Requirements and exact commands

Python 3.11+ is required. Extract the ZIP, then open a terminal in its parent folder.

```sh
cd phase-demo
python -m pip install -r requirements.txt
python main.py
```

The default command prints baseline metrics and saves `outputs/baseline/figure.png`.
No window or graphical desktop is required (Matplotlib Agg backend).

```sh
python -m unittest discover -s tests -v
python main.py --scenario all
python main.py --scenario noise --seed 42 --output-dir alternate-output
```

An isolated environment is optional: `python -m venv .venv`; activate using your OS's
standard command before installing requirements. No web service or database is needed.

## What is deliberately artificial

Observations are arbitrary scalars: configured base value + configured bias + seeded
Gaussian noise, in `synthetic_unit`. Dropout is a seeded Bernoulli draw. These values
contain **no emitter position information** and do not model RF propagation.

PlaceholderEstimator ignores observation values and receiver coordinates when constructing
its fixed, area-centered bell-shaped display fixture. It uses observation metadata only
to validate inputs. Noise and bias alter saved observations, but not the fixed spatial
distribution. A successful dropout experiment can also retain the same shape. This is
intentional; it must not be interpreted as robustness or graceful uncertainty degradation.

The configured placeholder width is a display-fixture setting, not measurement accuracy.
`OK` means the software contract succeeded, not successful physical localization.
The grid maximum is called a **MAP-like grid maximum**. Equal maxima use NumPy's
first row-major index; this explains the default (49,49), near the center of a 100 m square.

## Architecture and truth isolation

`ExperimentConfig` contains all setup and evaluation settings. The runner passes only
`EstimatorConfig`, observations, and receiver metadata to the estimator. That restricted
configuration has no emitter coordinates, evaluation thresholds, or ground-truth object.
The synthetic generator also has no position or ground-truth argument.

After estimation, the runner constructs GroundTruth for evaluation and evaluation-mode
visualization. It serializes truth separately from observations. Estimators must not read
output files. This is a software boundary, not an adversarial filesystem sandbox.

Tests check the actual call boundary with a spy, prohibit truth imports/access in the
localization package, and verify that changing truth does not change observations or the
estimate. The estimator is injectable via the Estimator protocol without changing the
evaluator, plotting code, or runner.

## Settings

All settings live in frozen dataclasses in `config.py`. Use `dataclasses.replace` for
programmatic configurations. Built-in scenarios require no manual editing. CLI overrides
are available for scenario, seed, and output directory.

Settings cover seed; width/height/resolution; receiver coordinates/enabled state;
test-emitter coordinates; arbitrary synthetic base/noise/bias/dropout; measurement and
evaluation timestamps; maximum age; evaluation thresholds; and fixture width.
Area dimensions must be integer multiples of resolution. Grid cells are centered in
equal-area footprints covering the full area. Phase 1 caps the grid at one million cells.

## Model regions and metrics

Cells are sorted by descending mass and accumulated to reach 0.50 or 0.90. All exact
ties at the cutoff are included, so actual mass may exceed the requested mass. A tiny
floating-point tolerance handles decimal cumulative sums. Cell count times resolution
squared gives area in m². The JSON also reports actual included mass.

These are regions of the **model's normalized distribution**, not empirically calibrated
confidence regions. A single inclusion flag is not a coverage estimate. Coverage across
trials and genuine accuracy benchmarking are outside this placeholder demonstration.

Truth inclusion uses the truth-containing cell footprint, not the nearest arbitrary
grid point. Interior boundaries belong to the cell on the positive side; the outermost
right/top boundaries belong to the last cell. Truth outside the area is not included.
Displayed contours interpolate the discrete region edge for visual guidance; metrics use
the exact boolean cell mask.

`overconfident_failure = error > large_error_threshold_m AND
region_90_area_m2 < small_uncertainty_area_threshold_m2`.
Defaults are 20 m and 1600 m², fixed demonstration choices, not operational acceptance
criteria. They are not tuned during execution. Failed estimates have null metrics and
null overconfidence, never fabricated zero error or confidence.

## Failure and scenario behavior

| Scenario | Expected default state |
|---|---|
| baseline, noise, bias | OK (fixed placeholder only) |
| dropout | Seeded loss; OK with >=2 retained observations, otherwise INSUFFICIENT_DATA |
| stale | STALE_DATA |
| zero, one, disabled, wrong_emitter | INSUFFICIENT_DATA |
| unknown_receiver, nan | INVALID_INPUT |
| invalid_grid | ESTIMATOR_FAILURE |

Two distinct active receivers are a pipeline demonstration gate, **not a claim of
localization observability**. Disabled receivers and unrelated emitter IDs are excluded.
Stale and bad-quality observations are excluded with diagnostic counters; fresh remaining
observations can still pass. Unknown receiver IDs, NaN/Inf values, incorrect units, future
timestamps, and duplicate receiver observations in a snapshot are rejected.
An all-stale selected stream yields STALE_DATA; one fresh usable observation yields
INSUFFICIENT_DATA. All-wrong-emitter input yields INSUFFICIENT_DATA and an ignored count.

Invalid output grids are not silently repaired. NaN failure fixtures are serialized as
JSON null plus `invalid_value: "NaN"`; no nonstandard JSON NaN tokens are written.
Malformed experiment configuration raises a clear ValueError before running a scenario.

## Output and reproducibility

Each `outputs/<scenario>/` directory contains config.json, emitter.json,
observations.json, ground_truth.json, metrics.json, and figure.png.
Rerunning a scenario overwrites only its named files in the selected output directory.

Same seed/config/environment gives identical observations and deterministic metrics.
**processing_time_ms is measured wall time and is necessarily excluded from equality.**
It covers the estimator call only, excluding simulation, evaluation, plotting, and I/O.
It is neither end-to-end latency nor a promised update rate.
Dependency versions/font rendering can affect cross-environment floating point/image bytes.
The tested versions are recorded in VALIDATION.md.

Expected default values (not real performance): estimate (49,49), truth (75,70),
error 33.42155 m, 50% area 448 m², 90% area 1472 m², both inclusion flags false,
active count 4, overconfident_failure true. Time varies each run.

## Scope boundary

Phase 1 and the Phase 1.5 validation harness are implemented. No RF localization method, signal classification,
motion/tracking, buildings, network delay simulation, hardware/SDR, cost optimization,
military integration, frontend framework, cloud service, ML, or Phase 2 functionality.

---

## Phase 2 — Generic Synthetic Sensor Telemetry Engine

Phase 2 is a separate `telemetry/` package, launched with `python -m telemetry`.
Existing commands and source files remain unchanged. It generates arbitrary scalar
values and imports no earlier-phase estimators, models, simulation or visualization
modules. Four independent streams use `SeedSequence([seed, sensor_index])` and NumPy
PCG64 generators. Changing faults for one stream cannot change any stream's values.

### Execution (Python 3.11+)

Run from the extracted `phase-demo` directory:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m unittest discover -s tests -p test_telemetry.py -v

# Live Matplotlib window, synthetic clock paced at real time (10 UI updates/s)
python -m telemetry --scenario telemetry/scenarios/mixed_faults.json

# Headless execution and PNG/CSV/JSON outputs
python -m telemetry --scenario telemetry/scenarios/normal.json --headless --output-dir telemetry_output/normal
python -m telemetry --scenario telemetry/scenarios/mixed_faults.json --seed 42 --headless --output-dir telemetry_output/mixed
python -m telemetry --scenario telemetry/scenarios/outage_recovery.json --headless --output-dir telemetry_output/outage

# Exact recorded-message replay (no random generation)
python -m telemetry --replay telemetry_output/mixed/recording.json --headless --output-dir telemetry_output/replay

# Replay in the live dashboard at double speed
python -m telemetry --replay telemetry_output/mixed/recording.json --speed 2
```

A graphical Matplotlib backend (for example TkAgg with Tk installed) is needed for
the live window. Headless mode needs no GUI. `--seed` is forbidden with `--replay`.
The seed is a nonnegative integer. Deterministic regenerated random values assume
the same NumPy implementation; recorded replay stores exact values and does not
invoke the generator. Closing the window ends playback; exported reports cover the
complete recording, while the PNG captures the last displayed time.

### Source layout

| File | Responsibility |
| --- | --- |
| `telemetry/schema.py` | Strict message validation and quality/health enumerations |
| `telemetry/engine.py` | Configuration, independent generation, fault injection, monitoring, replay, exports |
| `telemetry/dashboard.py` | Live status table and measured-value plots |
| `telemetry/__main__.py` | Independent command-line entry point |
| `telemetry/scenarios/*.json` | Normal, mixed faults and outage/recovery examples |
| `tests/test_telemetry.py` | Schema, fault, health, replay, export and dashboard tests |
| `PHASE2_VALIDATION.md` | Actual execution results and limitations |

### Strict message schema

Each message contains exactly these five fields; arrival time belongs to the
transport envelope, not the message. Units are synthetic seconds and arbitrary
scalar units. Streams use IDs `sensor-1` through `sensor-4`, start at time zero,
and sequence numbers start at zero.

| Field | Type and contract |
| --- | --- |
| `sensor_id` | Nonempty string; must identify a registered stream at ingestion |
| `timestamp` | Finite nonnegative real number; equals sequence × period |
| `sequence_number` | Nonnegative integer (booleans rejected), less than configured sample count |
| `measurement_value` | Finite real number (booleans rejected); operational valid range is [-100, 100] |
| `quality_flag` | String `GOOD` or `BAD` |

Missing/extra fields, malformed values, future timestamps and schedule violations
are rejected. An attributed rejection increments that sensor's invalid count.
Unknown or unidentifiable IDs increment the report's `rejected_unknown` counter.
A well-formed `BAD` or out-of-range measurement counts as a received transport
packet, but does not update the latest usable measurement or good-message clock.
Nonfinite values are rejected in memory; portable saved recordings require strict
JSON (no NaN or Infinity). Built-in invalid faults use `BAD` with a finite value.

### Scenario configuration and fault semantics

All configuration fields are required. See the three example JSON files.
`period`, `delay_limit`, and `offline_after` are finite positive seconds;
`offline_after` must exceed `delay_limit`. `samples` and `recovery_messages` are
positive integers. A stream can have the following fault entries:

```json
{
  "sensor-1": {
    "drop": [5, 6],
    "duplicate": [9],
    "invalid": [12],
    "delay": {"15": 2.0}
  }
}
```

Lists contain scheduled sequence numbers; delay keys are canonical nonnegative
integer strings and values are additional seconds. Drop takes precedence. Delay
can cause reordering when later sequence numbers arrive first. Duplicate injection
copies the event at the same arrival time. Measurement draws occur independently
of delivery/fault decisions. Equal-time events have a stable order.

### Monitoring definitions

- **Missing:** an unseen sequence below the highest received sequence, or a
  scheduled sequence whose delivery deadline has been reached. Known start time,
  period and sample count allow detection of initial and trailing omissions,
  including a completely silent sensor. The deadline is timestamp + delay limit;
  equality reaches the deadline. A later valid-schema packet resolves that gap.
- **Duplicate:** a repeated accepted sequence number; it does not increase unique
  received count, rate, latency samples or usable history, and cannot restore liveness.
- **Delayed:** arrival minus timestamp is greater than or equal to `delay_limit`.
- **Out of order:** a first arrival with sequence below the previously highest
  received sequence. Late packets cannot overwrite a newer latest measurement.
- **Invalid:** schema/stream contract failure, `BAD` quality or out-of-range value.
- **Rate:** unique accepted packets in the trailing one-second window `(t-1, t]`.
  This includes well-formed bad-quality packets. Startup is not annualized.
- **Packet loss:** currently unresolved missing / (unique received + unresolved
  missing). This is provisional and can decrease after late delivery; it is not a
  permanent loss verdict. Future scheduled messages are not included.
- **Latency:** latest and mean arrival-minus-source time for unique accepted
  packets, including bad-quality packets. Null means no sample is available.
- **Errors:** category counters are cumulative and may overlap on one packet.
  `missing_detected_total` counts each sequence gap once even if recovered.
  `error_count` sums that total and all four event error counters.

### Health transitions

Sensors start `RECOVERING`. Consecutive clean, unique messages reach `HEALTHY`
after `recovery_messages` arrivals. A newly detected gap or erroneous event resets
the clean streak and produces `DEGRADED`. No usable unique message for
`offline_after` seconds produces `OFFLINE`; before the first usable message,
timeout is measured from zero. Duplicate or invalid packets do not postpone it.
Clean arrivals resume `RECOVERING` then `HEALTHY`. Health describes recent service:
old cumulative errors/unresolved old gaps remain visible after recovery. A delayed
but usable first arrival restores liveness in `DEGRADED`, not `HEALTHY`.

### Replay, exports and boundaries

`Engine.advance(t)` processes every queued event up to monotonically increasing
virtual time, independent of dashboard frame rate. `seek(t)` resets and replays
from the beginning. No wall clock enters metrics. The recording includes version,
configuration, exact transport envelopes and an explicit end time that covers the
last scheduled deadline and any later injected arrival. Replay validates envelope
ordering, times and configuration and reports malformed message payloads.

Every CLI run writes:

- `recording.json`: full portable replay input.
- `report.json`: summary time, unknown-message count and per-sensor statistics.
- `report.csv`: the same per-sensor rows (null values are empty CSV cells).
- `messages.csv`: arrival time and exact message JSON, preserving malformed payloads.
- `dashboard.png`: status table and scalar history; missing intervals have plot gaps.

Example executed outputs are in `telemetry_examples/`. All stream metadata and
messages are synthetic. There is no network transport, RF model, location estimate,
tracking or sensor fusion. This is a finite educational in-memory engine: full
recordings, received sequence identities, latency samples and histories are retained;
it is not an unbounded production ingestion service. The plot displays up to 300
usable samples per stream. No additional framework dependencies were added.

---

## Phase 3 — Integrated Synthetic Sensor Dashboard

One Matplotlib window pairs the authored demo map with the Phase 2 telemetry
engine. Both are driven by one logical clock. They remain independent data paths:
**telemetry never enters MockEstimator, PlaceholderEstimator or a map calculation.**
The permanent screen labels are `SYNTHETIC DEMONSTRATION` and
`PREDEFINED POSITIONS — NOT SENSOR-DERIVED`.

### Exact commands

From the extracted `phase-demo` directory (Python 3.11+):

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m unittest discover -s tests -p test_integrated.py -v

python main.py --integrated normal
python main.py --integrated uncertain
python main.py --integrated lost
python main.py --integrated normal --presentation --speed 2 --seed 42

python main.py --integrated normal --headless --save both --presentation
python main.py --integrated uncertain --headless --save both --presentation
python main.py --integrated lost --headless --save both --presentation

python main.py --integrated-replay outputs/integrated/normal/replay_manifest.json --headless --save frames --output-dir replay_outputs
```

`--output-dir` defaults to `outputs`. Exports use its `integrated/<scenario>/`
subdirectory. `--save` accepts `frames`, `gif`, or `both`. On a headless system,
the integrated command exports both formats by default; a GUI backend opens an
interactive window, initially paused. With `--save` and a GUI, export finishes
before opening the window. No FFmpeg, browser, server or new framework is needed.
Pillow (already a Matplotlib dependency) writes GIFs. Missing visualization imports
produce a CLI error naming the dependency or suggesting headless mode.

### Architecture

| Module | Responsibility |
| --- | --- |
| `integrated/timeline.py` | Logical time, playback state, speed, seek bounds |
| `integrated/controller.py` | Synchronize DemoPlayer and telemetry Engine; deterministic reconstruction |
| `integrated/scenarios.py` | Explicit pairings; reuse strict existing scenario/config loaders |
| `integrated/dashboard.py` | Map, four status cards, widgets and wall-time adapter |
| `integrated/reporting.py` | Self-contained replay, CSV/JSON reports, PNG/GIF export |

Only `main.py` dispatch and README were changed among pre-existing files. Demo,
telemetry, evaluation, estimator code and all 83 existing tests remain unchanged.
The existing DemoPlayer reads authored frames; MockEstimator receives only its
frame index to draw the same visual fixture as the previous demo. The integrated
layer does not submit its data to any evaluation/localization pipeline.

### Presentation pairings

| Integrated selection | Authored demo | Independent telemetry |
| --- | --- | --- |
| NORMAL | `demo/scenarios/normal.json` | `telemetry/scenarios/normal.json` |
| UNCERTAIN | `demo/scenarios/uncertain.json` | `telemetry/scenarios/mixed_faults.json` |
| LOST | `demo/scenarios/lost.json` | `telemetry/scenarios/outage_recovery.json` |

These pairings have no causal meaning. In LOST, for example, a card can be HEALTHY
while the authored map has no current position. No map position, visual radius,
confidence label or trajectory is inferred from measurements. The recent trajectory
contains at most 15 past authored frames and breaks across missing positions.
The current marker, visual blob and ring disappear when the authored position is null.

### Clock and controls

- PLAY advances the shared logical clock. PAUSE stops both components.
- RESET returns to time zero and pauses; time-zero packets are processed, not discarded.
- 0.5x, 1x and 2x change logical seconds advanced per elapsed UI second.
- The TIME slider reconstructs both states from the beginning. No future telemetry
  counters, latest measurement or path points survive a backward seek. Seeking
  preserves playing/paused status except at the terminal time, which pauses.
- Selecting NORMAL, UNCERTAIN or LOST loads a fresh pair at zero and pauses,
  retaining the selected seed and speed. Failed scenario loading leaves the current
  controller intact.
- A 100 ms UI timer supplies elapsed wall time to the clock. Logical-state tests,
  direct API replay and export require no wall time.

The common duration is the maximum of authored map duration and telemetry end.
Built-ins run to **30.75 seconds**: the map ends at 30 seconds and the telemetry
engine finishes its final delivery deadline at 30.75. The map holds its exact last
frame during that tail and explicitly labels the hold; no new position is created.
DemoPlayer's local elapsed time saturates at 30, while the shared logical clock and
telemetry continue to 30.75. If a custom map is longer, only the telemetry monitor
horizon is extended; raw messages are unchanged and health may become OFFLINE.

### Sensor cards and integrity

Cards show the actual telemetry engine health, latest usable scalar, last accepted
message source timestamp/sequence, unique arrival rate, provisional packet loss,
missing/duplicate/delayed/invalid/out-of-order counts and latest latency. Health
logic is reused unchanged. All Phase 2 rate, deadline, validity and recovery
semantics still apply. Old error/loss counters can coexist with recovered health.

Last-message metadata follows the latest consumed valid-schema envelope, including
bad-quality and duplicate packets; latest usable value follows the engine's newer
usable sequence. A delayed envelope may therefore show an older source timestamp.
These fields are labeled separately. Empty streams display unavailable values and
become OFFLINE after the engine timeout; no fake measurements are added. The bottom
summary aggregates only telemetry counts/rates and shows unknown-ID rejects.

### Replay and outputs

`replay_manifest.json` embeds the validated authored scenario and exact telemetry
recording, plus logical time, speed and playing state. Loading it requires no source
scenario files or random regeneration. It restores the saved time; exported manifests
are at the final time, so click RESET then PLAY for an interactive replay. Manifest
speed/seed override the generic CLI defaults; to change interactive speed, use the
speed buttons. Invalid schema, missing files, nonfinite/out-of-bounds times and
unknown pairings produce explanatory errors. Each seek replays from the beginning;
no unverified checkpoints are used.

Full headless export writes:

- `frame_000.png` … `frame_062.png`: 63 frames at 0.5-second logical intervals,
  plus the exact 30.75-second terminal frame (when frames/both requested).
- `animation.gif`: the same states (when gif/both requested). Frame hold durations
  follow logical timestamps divided by speed, rounded to GIF's 10 ms units;
  the last frame holds for an additional 0.5 logical seconds.
- `replay_manifest.json`: complete replay inputs and terminal playback state.
- `integrated_state.json`: terminal map and telemetry logical state.
- `telemetry_summary.csv` / `report.csv`: identical terminal per-sensor statistics.
- `report.json`, `messages.csv`: original telemetry exports for the terminal state.
- `export_info.json`: exact frame times, speed and final GIF hold convention.

Exports always cover the entire pair, then restore the on-screen time and playing
state. The GIF is written to a temporary file, fully decoded and checked for frame
count before replacing the final file. Logical replay is deterministic; image byte
identity across different fonts, backends or dependency versions is not promised.

Executed example exports are in `phase3_examples/integrated/`. Each scenario contains
63 PNGs, a GIF and the reports. `phase3_preview/` contains selected presentation
screenshots. `PHASE3_VALIDATION.md` and `phase3_validation/` record actual results.

### Known limits and compatibility

The engine is finite and in memory. Seek rebuilds all consumed state and is suitable
for these short demos, not a long-running production recorder. GIF export retains
frames in memory. The native desktop window was not manually operated in this
headless environment; widget callbacks, timer adapter, rendering and exports were
executed under Agg. Presentation mode enlarges headings/health labels.

No RF propagation, measurement-derived location, direction finding, tracking, fusion,
hardware acquisition or weapon interface is implemented. Existing commands remain:

```bash
python main.py
python main.py --demo normal
python main.py --monte-carlo 100
python -m telemetry --scenario telemetry/scenarios/normal.json
```

Earlier validation reports describe their historical release. Phase 1.5 replay
manifests fingerprint source files; use their originating release for an old manifest.
Newly generated manifests work with this release; source-integrity checks were not weakened.
