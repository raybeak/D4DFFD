# phase-demo — File-by-File Cheat Sheet

> Everything here is **synthetic**. No file does real RF localization, tracking, or hardware I/O.
> Positions in the demo/integrated views are **hand-authored JSON**, and the Phase 1 "estimator" returns a **fixed bell-shaped fixture**.

Legend: 🎯 purpose · 🔑 key symbols · ⚠️ gotcha / review note (✅ = verified by running it)

---

## 0. Commands at a glance

Run from `phase-demo/` with the venv python (`../.venv/bin/python`). Add `--headless` on machines without a display.

| Goal | Command |
|---|---|
| All tests (112) | `python -m unittest discover -s tests -v` |
| Phase 1 baseline | `python main.py` → `outputs/baseline/` |
| Phase 1 all scenarios | `python main.py --scenario all` |
| Phase 1.5 batch | `python main.py --monte-carlo 100 --seed-start 42 --output-dir DIR` |
| Rebuild reports only | `python main.py --report --output-dir DIR` |
| Exact replay | `python main.py --replay DIR/experiment_manifest.json --output-dir DIR2` |
| Compare two batches | `python main.py --compare A/summary.csv B/summary.csv --output-dir DIR3` |
| Demo (scripted map) | `python main.py --demo {normal,uncertain,lost} [--headless --save both --presentation]` |
| Phase 2 telemetry | `python -m telemetry --scenario telemetry/scenarios/mixed_faults.json [--headless --output-dir D]` |
| Telemetry replay | `python -m telemetry --replay D/recording.json --headless --output-dir D2` |
| Phase 3 integrated | `python main.py --integrated {normal,uncertain,lost} [--headless --save both]` |
| Integrated replay | `python main.py --integrated-replay outputs/integrated/normal/replay_manifest.json --headless` |

---

## 1. How the pieces connect

```
Phase 1 / 1.5 (experiment pipeline)
  config.py ──► simulation/synthetic.py ──► localization/placeholder.py ──► evaluation/metrics.py ──► visualization/plot.py
                 (random scalars)            (fixed fixture, sees only        (truth built AFTER          (figure.png)
                                              EstimatorConfig + observations)   the estimate)
  experiments/baseline.py runs one trial; experiments/validation_harness.py repeats it N times
  ──► evaluation/aggregation.py (stats) ──► visualization/validation_plots.py, evaluation/comparison.py

Demo (separate)
  demo/scenarios/*.json ──► demo/scenario.py ──► demo/player.py (clock) ──► demo/mock_estimator.py (blob) ──► demo/dashboard.py

Phase 2 (separate, imports nothing from earlier phases)
  telemetry/scenarios/*.json ──► telemetry/engine.py (generate ► Engine) ──► telemetry/dashboard.py

Phase 3 (pairs Demo + Phase 2 on one clock; data paths stay independent)
  integrated/scenarios.py ──► integrated/controller.py (+ timeline.py) ──► integrated/dashboard.py / reporting.py
```

The `main.py` CLI dispatches everything except Phase 2, which has its own `telemetry/__main__.py`.

---

## 2. Top-level source

### `main.py`
- 🎯 CLI entry point for Phase 1/1.5, the Demo, and Phase 3. The modes are mutually exclusive: `--monte-carlo | --report | --compare | --replay | --demo | --integrated | --integrated-replay`.
- 🔑 `main()`. Experiment modules are imported lazily, so the Phase 1 `Agg` backend doesn't block interactive demo windows.
- ⚠️ ✅ `--seed-start` without `--monte-carlo` is silently ignored. No error is raised.
- ⚠️ ✅ A malformed manifest passed to `--replay` or `--report` crashes with a raw `KeyError` traceback. Only `ValueError` and `OSError` are turned into clean CLI errors.
- ⚠️ The `--demo` branch doesn't catch `ImportError`, but the `--integrated` branch does.

### `config.py`
- 🎯 Frozen dataclasses holding every setting.
- 🔑 `EstimatorConfig`: the **only** config the estimator sees (area, grid, emitter id, timestamps, fixture width). Its `validate()` enforces finite positive sizes, area divisible by resolution, and at most 1M cells.
- 🔑 `EvaluationThresholds`: 20 m error and 1600 m² area, used to flag overconfidence.
- 🔑 `ExperimentConfig`: seed 42, 4 receivers at the corners of a 100×100 m area, truth at (75, 70), plus noise, bias, and dropout settings.
- ⚠️ `ExperimentConfig.validate()` doesn't check receivers. The estimator rejects bad receiver metadata later.
- 💡 Change settings with `dataclasses.replace(ExperimentConfig(), random_seed=7)`.

### `requirements.txt`
- 🎯 `numpy>=1.24,<3` and `matplotlib>=3.7,<4`. Pillow comes in as a matplotlib dependency.

---

## 3. `models/`: plain frozen dataclasses

| File | Class | Fields |
|---|---|---|
| `emitter.py` | `Emitter` | `emitter_id`, `emitter_type="COOPERATIVE_SYNTHETIC_TEST"` |
| `receiver.py` | `Receiver` | `receiver_id`, `x`, `y`, `enabled=True` |
| `observation.py` | `Observation` | `timestamp`, `receiver_id`, `emitter_id`, `value`, `unit="synthetic_unit"`, `quality="VALID"` |
| `ground_truth.py` | `GroundTruth` | `timestamp`, `emitter_id`, `x`, `y` |
| `__init__.py` | (empty) | |

---

## 4. `simulation/`

### `simulation/synthetic.py`
- 🎯 Generates fake observations: `base + bias + N(0, noise)`, with seeded Bernoulli dropout per receiver.
- 🔑 `generate_observations(receivers, emitter_id, *, seed, timestamp, noise, bias, dropout, base_value)`
- ⚠️ It draws random numbers for every receiver, including disabled ones, so disabling one receiver doesn't shift the others' values. This is intentional.
- ⚠️ It has **no position input**, so the values carry no location information.

---

## 5. `localization/`

### `localization/interface.py`
- 🎯 The contract at the estimator boundary.
- 🔑 `Status` (enum): `OK`, `INSUFFICIENT_DATA`, `STALE_DATA`, `INVALID_INPUT`, `ESTIMATOR_FAILURE`.
- 🔑 `LocalizationResult`: probability grid, x/y coordinates, representative position, status, active observation count, diagnostics.
- 🔑 `Estimator` (Protocol): `estimate(observations, receivers, config) -> LocalizationResult`. Implement this to plug in a real algorithm.
- 🔑 `validate_grid()`: requires a finite, nonnegative grid that sums to 1 (±1e-10) over strictly increasing coordinates. It never repairs a grid.

### `localization/placeholder.py`
- 🎯 `PlaceholderEstimator` validates its inputs, then returns a **fixed Gaussian centered on the area**. It ignores observation values entirely.
- 🔑 Filtering order: wrong emitter (ignored) → unknown receiver (`INVALID_INPUT`) → disabled → NaN or wrong unit (`INVALID_INPUT`) → future timestamp (`INVALID_INPUT`) → stale → bad quality.
- 🔑 Fewer than 2 active observations gives `STALE_DATA` if everything was stale, otherwise `INSUFFICIENT_DATA`. Duplicate receivers in one snapshot give `INVALID_INPUT`.
- 🔑 `_fixture()` is the override point. Tests use it to inject a broken grid.
- ⚠️ With equal grid values, argmax picks the first index, so the "estimate" is always (49, 49) and the baseline error is always 33.42 m.

---

## 6. `evaluation/`

### `evaluation/metrics.py`
- 🎯 Scores one result against the truth.
- 🔑 `model_region(grid, mass, cell_area)`: the highest-mass cells that reach 50% or 90%. **All ties at the cutoff are included**, with a tolerance of 8·eps.
- 🔑 `contains(region, result, truth)`: tests the truth point against cell footprints (left-closed cells; the outer edge counts as inside).
- 🔑 `evaluate(...) -> dict`: error, region areas and actual masses, inside flags, and `overconfident_failure = error > 20 m AND area90 < 1600 m²`. Results that aren't OK get `None` metrics, never zeros.

### `evaluation/aggregation.py`
- 🎯 Turns trial dicts into validated rows and summary statistics.
- 🔑 `TRIAL_FIELDS`, `SUMMARY_FIELDS`, `STATUSES`, `CALIBRATION_LABEL`
- 🔑 `trial_row()` and `validate_trial()`: strict typing, nested regions (50 ≤ 90), and no scores on failed trials.
- 🔑 `summarize(rows, scenario)`: mean, median, population std, p90, p95, and max error; median areas; coverage over **OK trials only**; status counts over **all** trials.
- 🔑 `collect_overconfident(rows)`

### `evaluation/comparison.py`
- 🎯 Computes CANDIDATE − BASELINE deltas between two `summary.csv` files. Descriptive only.
- 🔑 `compare_summaries(baseline, candidate, output) -> rows`, which writes `regression_comparison.csv`. Rate deltas are in percentage points. A missing value gives `MISSING_VALUE_OR_SCENARIO`.

---

## 7. `experiments/`

### `experiments/baseline.py`
- 🎯 Runs a single trial: generate → estimate (timed) → build truth → evaluate → write JSON files and the figure.
- 🔑 `SCENARIOS`: baseline, noise, dropout, bias, stale, zero, one, disabled, unknown_receiver, wrong_emitter, nan, invalid_grid
- 🔑 `scenario_config(base, name)` applies the config changes for a scenario. `run_experiment(config, scenario, output_dir, estimator=None, make_plot=True)`.
- ⚠️ The `one`, `unknown_receiver`, `wrong_emitter`, and `nan` scenarios edit the observations **after** generation. `invalid_grid` swaps in a subclass whose fixture is all zeros.
- ⚠️ NaN values are written to JSON as `null` plus `"invalid_value": "NaN"`, keeping the JSON strict.

### `experiments/validation_harness.py` (Phase 1.5)
- 🎯 Runs repeated trials and writes reports, a manifest, and supports exact replay.
- 🔑 `run_batch(config, scenarios, seed_start, n, output_dir, trial_executor=run_experiment)`. Any `Exception` inside a trial becomes an `ESTIMATOR_FAILURE` row and the batch continues.
- 🔑 `write_reports()` writes trials, summary, overconfident_failures, and failure_taxonomy CSVs, plus the plots.
- 🔑 `regenerate_reports(dir)` rebuilds reports from `trials.csv` without rerunning anything, after checking trial identities against the manifest.
- 🔑 `replay_manifest(path, out)` refuses to run unless the Python version, dependency versions, and **SHA-256 of every `.py` file** match.
- ⚠️ ✅ The source hashes include `tests/*.py`, so editing any test or adding any `.py` file breaks `--replay` of older manifests.
- ⚠️ A broad `except Exception` is used on purpose to record per-trial failures. `KeyboardInterrupt` and `SystemExit` still propagate.

---

## 8. `visualization/`

| File | 🎯 What it draws |
|---|---|
| `plot.py` | `plot_experiment()`: heatmap, 50% and 90% contours, estimate marker (X), receivers, and truth marker (★), saved as `figure.png`. Forces the `Agg` backend at import. |
| `validation_plots.py` | `create_validation_plots()`: three boxplots (error, areas, timing) and `coverage_comparison.png`. Labels empty or all-failed batches explicitly. |
| `__init__.py` | (empty) |

⚠️ Both files call `matplotlib.use("Agg")` at import. That's why `main.py` imports them lazily.

---

## 9. `demo/`: scripted map replay

| File | 🎯 / 🔑 |
|---|---|
| `scenario.py` | Strict JSON loader. `load_scenario(path)` and `builtin_scenario(name)` return `DemoScenario` and `DemoFrame` objects. It rejects unknown fields, bad states, non-increasing times, positions outside the area, and LOST frames that have a position. |
| `player.py` | `DemoPlayer` holds the deterministic clock: `play`, `pause`, `reset`, `seek`, `advance(wall_s)`, and speed (0.5, 1, or 2 only). It uses `bisect` to show the latest frame at or before the current time (no interpolation) and keeps up to 15 frames of history. |
| `mock_estimator.py` | `MockEstimator(scenario).estimate(frame_index)` copies the position from JSON and builds a visual Gaussian with σ = radius/2. A null position gives `INSUFFICIENT_DATA` with no grid. The observations argument is ignored. |
| `dashboard.py` | `DemoDashboard` is the matplotlib UI: blob, ring, tail, status panel, PLAY/RESET buttons, keys Space, R, 1, 2, 3. `export_demo()` writes PNG frames and a GIF (written to a temp file and checked before replacing the old one). `run_demo()` falls back to headless automatically when Linux has no `DISPLAY`. |
| `scenarios/normal.json` | NORMAL_TRACK: 31 frames, moving from (20,20) to (80,78), radius shrinking from 24 m to 5 m. |
| `scenarios/uncertain.json` | UNCERTAIN_TRACK: radius fixed at 28 m, confidence always LOW. |
| `scenarios/lost.json` | LOST_TRACK: TRACKING → DEGRADED (8–9 s) → LOST (10–16 s) → REACQUIRING → TRACKING. |
| `__init__.py` | Docstring only. |

---

## 10. `telemetry/`: Phase 2 synthetic sensor streams

| File | 🎯 / 🔑 |
|---|---|
| `schema.py` | `Message` (exactly 5 fields, strict types, booleans rejected), `Quality` (GOOD/BAD), `Health` (HEALTHY/DEGRADED/OFFLINE/RECOVERING), `number()`. `Message.parse(raw)` raises `ValueError` only. |
| `engine.py` | `validate_config()`, `generate(config)` (4 streams, each with its own `SeedSequence([seed, i])`; faults are drop/duplicate/invalid/delay), `validate_recording()`, `save_recording()`/`load_recording()`. `Engine(recording)` has `advance(t)` (monotonic), `seek(t)` (reset and replay), `snapshot()`, `export(dir)`, and tracks missing, duplicate, delayed, out-of-order, and invalid messages, rate, loss, latency, and health. |
| `dashboard.py` | `Dashboard(recording)`: status table plus value plot with gaps where data is missing. `run(speed)` plays live on wall-clock time; `save(path)` writes a PNG. |
| `__main__.py` | `python -m telemetry` CLI with `--scenario` or `--replay`, plus `--seed`, `--headless`, `--speed`, `--output-dir`. Writes `dashboard.png`, `report.json`, `report.csv`, `messages.csv`, and `recording.json`. |
| `__init__.py` | Re-exports the public API. |
| `scenarios/normal.json` | 61 samples at 0.5 s each, no faults. |
| `scenarios/mixed_faults.json` | s1 drops, s2 duplicates plus a 2 s delay, s3 invalid values, s4 an 11-sample outage. |
| `scenarios/outage_recovery.json` | s2 drops sequences 8–19, then recovers. |

- ⚠️ ✅ **`Engine` gets quadratically slower as recordings grow.** `_clock()` rebuilds `set(range(due)) - seen` for every sensor on every event. Measured: 2k samples took 2.3 s, 4k took 9 s, 8k took 39 s. The built-in scenarios have 61 samples, so they aren't affected. Fixing it would mean tracking missing sequences incrementally.
- ⚠️ ✅ `--scenario` pointing at a JSON file whose top level isn't an object, combined with `--seed`, crashes with a raw `TypeError`. `integrated/scenarios.py` already guards against this case.
- ⚠️ Health changes in order: RECOVERING → (3 clean messages) → HEALTHY. Any error moves it to DEGRADED. No usable message for 2 s moves it to OFFLINE. Duplicate or invalid packets don't count as signs of life.

---

## 11. `integrated/`: Phase 3 single dashboard

| File | 🎯 / 🔑 |
|---|---|
| `timeline.py` | `Timeline(duration, speed)` is the one logical clock: `play`, `pause`, `reset`, `seek`, `advance(seconds)`. Speed must be 0.5, 1, or 2. |
| `scenarios.py` | `PAIRINGS`: normal↔normal, uncertain↔mixed_faults, lost↔outage_recovery. `load_pair()`, `parse_demo()` (writes a temp file so it can reuse the strict loader), `normalize_recording()` (extends `end_time` to the map duration), and the `DISCLAIMER` constants. |
| `controller.py` | `Controller` keeps `DemoPlayer` and the telemetry `Engine` on one clock. `advance` moves forward incrementally; `seek` and `reset` rebuild from zero. `switch(name)` builds the new controller first, so a failed switch leaves the current one intact. `snapshot()` adds last-message metadata for each sensor. `from_payload()` restores from a manifest. |
| `dashboard.py` | `IntegratedDashboard`: map, 4 sensor cards, totals line, PLAY/PAUSE/RESET, speed and scenario buttons, TIME slider. `run_integrated()` is called from `main.py`. |
| `reporting.py` | `manifest()`, `load_manifest()` (all errors become `ValueError`), `export_reports()`, `export_animation()` (63 frames at 0.5 s steps up to 30.75 s, plus a checked GIF; restores the on-screen state afterwards). |
| `__init__.py` | Exports `Controller`. |

- ⚠️ `Controller.switch()` always loads the **built-in** scenario files. A controller restored from a replay manifest or custom paths loses that source when you switch.
- ⚠️ `Controller.snapshot()` re-parses every event consumed so far on every render (every 100 ms). That's fine for 30 s demos but grows linearly with recording length.
- ⚠️ The pairings are presentation only. Telemetry never feeds the map.

---

## 12. `tests/` (112 tests, all passing)

| File | Covers |
|---|---|
| `test_data_separation.py` | The estimator sees only the restricted config; changing the truth doesn't change the estimate; `localization/` never imports truth. |
| `test_failures.py` | Zero, one, or disabled receivers; stale data and the age boundary; NaN; wrong emitter; dropout; invalid grid; bad config; duplicates and bad quality. |
| `test_metrics.py` | Euclidean error, strict thresholds, region ties, cell footprints, invalid grids, failed results stay unscored. |
| `test_reproducibility.py` | Same seed gives the same output; a different seed gives different observations. |
| `test_validation_harness.py` | Statistics, coverage denominators, failure accounting, CSV round trip, continuing after exceptions, manifest and replay, comparison math, empty and all-failed batches. |
| `test_demo.py` | JSON validation, exact positions, bounded history, missing frames, no interpolation, controls, GIF export and state restore. |
| `test_telemetry.py` | Schema, faults, delayed messages resolving loss, health transitions, rate window, replay step-size independence, exports, no imports from earlier phases. |
| `test_integrated.py` | Shared clock, seek leaks no future state, atomic switch, telemetry can't change the map, manifest round trip, export, error handling. |
| `__init__.py` | (empty) |

---

## 13. Docs and validation records (static, historical)

| File | What it is |
|---|---|
| `README.md` | Full spec for all phases. This is the source of truth for semantics. |
| `VALIDATION.md` | Phase 1.5 record: 42 tests, baseline numbers, Python 3.12 environment. |
| `DEMO_VALIDATION.md` | Demo record: 56 tests, 31 frames per scenario. |
| `PHASE2_VALIDATION.md` | Telemetry record: 83 tests, scenario outcomes. |
| `PHASE3_VALIDATION.md` | Integrated record: 112 tests, export checks. |
| `test-results.txt`, `demo-test-results.txt` | Saved `unittest -v` logs from earlier releases. |
| `phase3_validation/*.txt`, `telemetry_validation/*.txt` | Saved test and CLI logs from those releases. |
| `*-output.json` (top level, 11 files) | Captured stdout of earlier CLI runs, e.g. `baseline-output.json` = `python main.py`, `monte-carlo-output.json` = the 100-trial summary. |

---

## 14. Generated output folders (safe to regenerate; don't edit by hand)

| Folder | Produced by | Contents |
|---|---|---|
| `outputs/` | Default `--output-dir` | `baseline/` (Phase 1 files), the batch CSVs and PNGs, `trial_artifacts/`, `demo/`, `integrated/` |
| `demo_legacy/` | `main.py` run earlier | Phase 1 baseline files (config, emitter, observations, truth, metrics, figure) |
| `failure_demo/` | `--scenario all --monte-carlo 5` | Batch across all 12 scenarios |
| `demo_validation/`, `demo_replay/` | `--monte-carlo 100`, then `--replay` | Batch and its exact replay (~509 files each, mostly `trial_artifacts/`) |
| `replay_output/` | `--replay outputs/...` | Replay of the original batch |
| `comparison_output/`, `demo_comparison/` | `--compare` | `regression_comparison.csv` |
| `telemetry_output/`, `telemetry_examples/` | `python -m telemetry` | Recording, reports, messages, dashboard PNG |
| `phase3_examples/integrated/` | `--integrated … --save both` | 63 PNGs, a GIF, and reports per scenario |
| `phase3_preview/` | Screenshots | `normal.png`, `uncertain.png`, `lost.png` |
| `run_outputs/` | My run on 2026-10-10 | Fresh run of every command (65 MB, OK to delete) |
| `__pycache__/` | Python | Bytecode cache |

Per-trial layout: `trial_artifacts/<scenario>/<000000>/<scenario>/{config,emitter,observations,ground_truth,metrics}.json`.
⚠️ A shorter rerun into the same folder leaves old trial folders behind. The CSVs and manifest are authoritative.

---

## 15. Verified review findings (by priority)

1. **Telemetry engine is O(n²)** in recording length (`telemetry/engine.py`, `_clock`). It doesn't matter at 61 samples but makes long recordings impractical (8k samples took 39 s).
2. **Raw tracebacks on malformed input:** `main.py --replay`/`--report` with a manifest missing keys (`KeyError`), and `python -m telemetry --scenario` with a non-object JSON file plus `--seed` (`TypeError`). Fix by validating the manifest keys and the config type, or by catching `KeyError`/`TypeError` at the CLI.
3. **`--seed-start` is silently ignored** unless `--monte-carlo` is given. Consider `parser.error` here, as the code already does for `--speed` and the other demo-only flags.
4. **Replay is tied to test files as well as code:** any edit under `tests/` invalidates old manifests. This is by design, but easy to trip over.
5. **`Controller.switch` drops custom or replayed sources** and reloads the built-in pairings.
