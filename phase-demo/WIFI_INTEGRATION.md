# phase-demo → Wi-Fi Signal Detection Nodes: Integration Sheet

> **Nothing in the repo is removed or changed by this plan.** Every existing file stays as it is.
> Real-world support is **added as new files** next to the existing ones. The synthetic and demo parts stay available for tests, demos, and offline checks.

Legend: ✅ needed in live use · 🧪 needed only for testing/calibration (keep in repo) · 💤 not needed in live use (keep in repo)

---

## 1. Target setup

```
 ┌─────────────┐   Wi-Fi beacon frames    ┌──────────────┐
 │ Target tag  │ ───────────────────────► │ Node r1..rN  │  ESP32 / Raspberry Pi
 │ (your own   │   (known SSID / BSSID)   │ measures RSSI│  at surveyed (x, y)
 │  device)    │                          └──────┬───────┘
 └─────────────┘                                 │ JSON over MQTT / UDP / HTTP
                                                 ▼
                     ┌───────────────────────────────────────────────┐
                     │ NEW ingest service                            │
                     │  parse → validate → per-node windowed median  │
                     │  → models.Observation(unit="dBm")             │
                     └──────────────┬────────────────────────────────┘
                                    ▼
                     ┌───────────────────────────────────────────────┐
                     │ NEW localization/rssi_estimator.py            │
                     │  implements localization.interface.Estimator  │
                     │  → LocalizationResult (grid + position)       │
                     └──────────────┬────────────────────────────────┘
                                    ▼
                     ┌───────────────────────────────────────────────┐
                     │ NEW live dashboard + recorder                 │
                     │  (rendering copied from demo/dashboard.py)    │
                     └───────────────────────────────────────────────┘
```

**Recommended measurement method:** the **target is a cooperative beacon you own**, for example an ESP32 broadcasting a fixed SSID. Each node runs a normal Wi-Fi **scan** and reports the RSSI for that BSSID. This needs no monitor mode, no packet capture, and doesn't collect anyone else's traffic.

---

## 2. Responsible-use rules (read before deploying)

- Only locate **devices you own or have explicit consent to locate.**
- Passively capturing other people's frames (probe requests, MAC addresses) can be illegal interception or personal-data processing, depending on where you are. The scan-a-known-beacon approach avoids this.
- Keep the project's own scope: the README rules out military integration and weapon interfaces. Keep it to asset, indoor-positioning, and lab uses.
- If MAC addresses are ever stored, hash or rotate them and keep only what you need.

---

## 3. What maps to what

| Real world | Existing code it plugs into | Notes |
|---|---|---|
| Node and its surveyed position | `models/receiver.py` → `Receiver(receiver_id, x, y, enabled)` | Measure positions on the site's local x/y grid in metres. Set `enabled=False` for a node that's down. |
| Target tag | `models/emitter.py` → `Emitter(emitter_id)`; `EstimatorConfig.emitter_id` | Use the beacon's BSSID or a label for it. |
| One RSSI reading | `models/observation.py` → `Observation(timestamp, receiver_id, emitter_id, value, unit, quality)` | `value` = RSSI in dBm, `unit="dBm"`, `quality="VALID"` or something else. |
| Site area and grid | `config.py` → `EstimatorConfig(area_width_m, area_height_m, grid_resolution_m)` | Area must be a whole multiple of the resolution, with at most 1M cells. |
| Freshness window | `EstimatorConfig.maximum_observation_age` (default 5 s) and `evaluation_timestamp` | Live: `evaluation_timestamp = time.time()`. Older readings count as stale. |
| Position output | `localization/interface.py` → `LocalizationResult`, `Status` | The probability grid plus the most likely grid cell. |
| Estimator plug-in point | `localization/interface.py` → `Estimator` Protocol | New estimator. See §5. |
| Per-node health | Semantics from `telemetry/engine.py` (HEALTHY / DEGRADED / OFFLINE / RECOVERING) | Reuse the rules, not the class. See §6. |
| Accuracy at known points | `evaluation/metrics.py` → `evaluate()`; `evaluation/aggregation.py` | For calibration walks only. Needs ground truth. |
| Map rendering | `demo/dashboard.py`, `integrated/dashboard.py` | Copy the rendering code into a new live dashboard (§7). |

---

## 4. Node → server message (new wire format)

Each node sends roughly one message per scan:

```json
{
  "node_id": "r1",
  "target_id": "tag-01",
  "timestamp": 1760090000.125,
  "seq": 1532,
  "rssi_dbm": -63,
  "channel": 6
}
```

Ingest rules:
1. **Reject** unknown `node_id`, non-finite or out-of-range RSSI (keep −100 to 0 dBm), and timestamps in the future. This follows the strictness of `telemetry/schema.py`.
2. **Sync clocks** on every node with NTP or chrony. `maximum_observation_age` assumes they agree to well under a second.
3. **Aggregate per node** over a sliding window (e.g. the median of the last 2–3 s). The estimator expects **one observation per node per estimate**; `PlaceholderEstimator` returns `INVALID_INPUT` on duplicates, and the new estimator does the same.
4. Turn each node's window into `Observation(window_end_ts, node_id, target_id, median_rssi, unit="dBm")`.

```python
# NEW: ingest/aggregate.py (sketch)
from collections import defaultdict, deque
from statistics import median
from models.observation import Observation

class RssiWindow:
    def __init__(self, window_s: float = 3.0):
        self.window_s = window_s
        self.buffers: dict[tuple[str, str], deque] = defaultdict(deque)

    def add(self, node_id: str, target_id: str, ts: float, rssi_dbm: float) -> None:
        self.buffers[(node_id, target_id)].append((ts, rssi_dbm))

    def snapshot(self, target_id: str, now: float) -> tuple[Observation, ...]:
        out = []
        for (node_id, tid), buf in self.buffers.items():
            while buf and buf[0][0] < now - self.window_s:
                buf.popleft()
            if tid == target_id and buf:
                out.append(Observation(buf[-1][0], node_id, tid,
                                       float(median(v for _, v in buf)), unit="dBm"))
        return tuple(out)
```

---

## 5. New estimator: RSSI log-distance grid (✅ live)

The model: `RSSI(d) = P0 − 10·n·log10(d / d0)` with Gaussian noise of σ dB. It scores every grid cell, normalizes, and returns the same `LocalizationResult` contract as the placeholder, so `validate_grid`, `evaluate`, the plots, and the harness all keep working.

> I smoke-tested this exact code against the repo's interfaces on 2026-10-10. With noise-free synthetic RSSI from (75, 70) it returned (75, 69): 1 m error, truth inside the 90% region. With only 2 nodes it returns `INSUFFICIENT_DATA`.

```python
# NEW: localization/rssi_estimator.py
"""RSSI log-distance grid estimator. Model-based; calibrate P0/exponent/sigma per site."""
from dataclasses import dataclass, field
from typing import Sequence
import math
import numpy as np
from config import EstimatorConfig
from models.observation import Observation
from models.receiver import Receiver
from localization.interface import LocalizationResult, Status, validate_grid


@dataclass(frozen=True)
class PathLossModel:
    p0_dbm: dict = field(default_factory=dict)   # per-node RSSI at d0, from calibration
    default_p0_dbm: float = -40.0
    exponent: float = 2.7                        # ~2 open space, 2.7-4 indoors
    d0_m: float = 1.0
    sigma_db: float = 6.0                        # shadowing/multipath spread, from calibration


class RssiPathLossEstimator:
    def __init__(self, model: PathLossModel, min_receivers: int = 3):
        self.model, self.min_receivers = model, min_receivers

    def estimate(self, observations: Sequence[Observation], receivers: Sequence[Receiver],
                 config: EstimatorConfig) -> LocalizationResult:
        def failure(status: Status, message: str, count: int = 0) -> LocalizationResult:
            return LocalizationResult(None, np.array([]), np.array([]), None, status, count,
                                      config.evaluation_timestamp, config.emitter_id,
                                      config.grid_resolution_m, message)
        try:
            config.validate()
        except ValueError as exc:
            return failure(Status.INVALID_INPUT, str(exc))
        lookup = {r.receiver_id: r for r in receivers}
        active, stale = [], 0
        for obs in observations:
            if obs.emitter_id != config.emitter_id:
                continue
            if obs.receiver_id not in lookup:
                return failure(Status.INVALID_INPUT, f"Unknown receiver {obs.receiver_id}")
            if not lookup[obs.receiver_id].enabled:
                continue
            if obs.unit != "dBm" or not math.isfinite(obs.value) or not math.isfinite(obs.timestamp):
                return failure(Status.INVALID_INPUT, "Expected finite RSSI in dBm")
            age = config.evaluation_timestamp - obs.timestamp
            if age < 0:
                return failure(Status.INVALID_INPUT, "Future observation timestamp")
            if age > config.maximum_observation_age:
                stale += 1
                continue
            if obs.quality == "VALID":
                active.append(obs)
        if len({o.receiver_id for o in active}) != len(active):
            return failure(Status.INVALID_INPUT, "Aggregate to one observation per receiver first")
        if len(active) < self.min_receivers:
            status = Status.STALE_DATA if not active and stale else Status.INSUFFICIENT_DATA
            return failure(status, f"Need >= {self.min_receivers} receivers", len(active))
        step = config.grid_resolution_m
        x = (np.arange(round(config.area_width_m / step)) + 0.5) * step
        y = (np.arange(round(config.area_height_m / step)) + 0.5) * step
        xx, yy = np.meshgrid(x, y)
        m = self.model
        log_likelihood = np.zeros_like(xx)
        for obs in active:
            r = lookup[obs.receiver_id]
            d = np.maximum(np.hypot(xx - r.x, yy - r.y), m.d0_m)
            p0 = m.p0_dbm.get(obs.receiver_id, m.default_p0_dbm)
            predicted = p0 - 10 * m.exponent * np.log10(d / m.d0_m)
            log_likelihood += -0.5 * ((obs.value - predicted) / m.sigma_db) ** 2
        weights = np.exp(log_likelihood - log_likelihood.max())
        grid = weights / weights.sum()
        try:
            validate_grid(grid, x, y)
        except ValueError as exc:
            return failure(Status.ESTIMATOR_FAILURE, str(exc), len(active))
        iy, ix = np.unravel_index(np.argmax(grid), grid.shape)
        return LocalizationResult(grid, x, y, (float(x[ix]), float(y[iy])), Status.OK, len(active),
                                  config.evaluation_timestamp, config.emitter_id, step,
                                  "RSSI path-loss grid (model-based, calibrate per site)")
```

Why it's built this way:
- It uses **3 nodes at minimum** for 2D. The placeholder's 2-node gate is a pipeline check, not a sound requirement for localization.
- Calibration values go in a **separate `PathLossModel`**, so the frozen `EstimatorConfig` (and every test that uses it) stays untouched.
- The `unit="dBm"` check deliberately keeps synthetic data (`"synthetic_unit"`) out of the real estimator. The placeholder rejects `"dBm"` for the same reason in reverse.

**What to expect:** indoor RSSI is noisy (multipath, bodies, walls), so expect **errors of a few metres or more**. In the smoke test, σ = 6 dB gave a 90% region of about 2,900 m² even with perfect input. Get your site's real numbers from calibration (§8) before trusting any output.

---

## 6. Node health monitoring (✅ live, reusing the rules)

The Phase 2 health rules carry over well:

| Rule (from `telemetry/engine.py`) | Live meaning |
|---|---|
| RECOVERING → HEALTHY after `recovery_messages` clean messages | A node that just came back must prove itself first |
| DEGRADED on gap, duplicate, delay, or invalid | Missed scans, replayed packets, late delivery, bad RSSI |
| OFFLINE after `offline_after` s with no usable message | Set `Receiver.enabled=False` for estimation |
| Rate = unique messages in trailing 1 s | Scan rate per node |

But **don't feed live data into `telemetry.Engine` itself.** It's built for finite, pre-recorded streams:
- Sensor IDs are fixed: `IDS = sensor-1..sensor-4`.
- It requires `timestamp == sequence_number × period` exactly, which real Wi-Fi scans won't meet.
- It needs `samples` (the total message count) up front, and gets **O(n²)** slower as messages accumulate (8k messages took 39 s).

Write a small `NodeMonitor` that applies the same rules incrementally: keep the last-seen time, a clean-message streak, and counters per node. Copy the thresholds from `telemetry/scenarios/normal.json` as starting values.

---

## 7. Live loop and dashboard (✅ live, new files)

```python
# NEW: live/run_live.py (sketch)
import time
from dataclasses import replace
from config import ExperimentConfig
from localization.rssi_estimator import RssiPathLossEstimator, PathLossModel

base = ExperimentConfig()                 # replace receivers with your surveyed nodes
receivers = base.receivers                # Receiver("r1", x, y), ...
estimator = RssiPathLossEstimator(PathLossModel(p0_dbm={"r1": -41.5, "r2": -39.8}))

while True:
    now = time.time()
    cfg = replace(base.estimator, emitter_id="tag-01", evaluation_timestamp=now)
    observations = window.snapshot("tag-01", now)                  # from §4
    live_receivers = monitor.apply_enabled(receivers)              # OFFLINE → enabled=False (§6)
    result = estimator.estimate(observations, live_receivers, cfg)
    dashboard.show_result(result)                                  # §7 below
    recorder.append(now, observations, result)                     # raw log for replay
    time.sleep(1.0)
```

For the dashboard, **copy rather than reuse** the rendering from `demo/dashboard.py` (`blob.set_data(grid)`, marker, ring, gap text) or the card layout from `integrated/dashboard.py`. Reasons:
- Both existing dashboards print **"SIMULATED / PREDEFINED DATA"** and **"NOT SENSOR-DERIVED"** labels, which would be false on live data. Those labels are correct for the demo, so leave them there.
- They're driven by `DemoPlayer` and `MockEstimator` (authored frames), not by a live `LocalizationResult`.
- Draw the ring from the actual 90% model region (`evaluation/metrics.py::model_region`, as `visualization/plot.py` does), not from an authored radius.
- Show the result's `Status` (OK, INSUFFICIENT_DATA, STALE_DATA, …) prominently, and hide the marker whenever it isn't OK.

**Recording:** log the raw node messages (JSON lines) plus each estimate. That gives you offline replay and re-tuning without hardware, in the same spirit as `telemetry` recordings and the replay manifests.

---

## 8. Calibration and accuracy testing (🧪 run before go-live and after layout changes)

This is where the Phase 1.5 harness becomes useful with real data.

1. **Per-node P0:** put the tag 1 m from each node, record about 60 s, and use the median RSSI → `PathLossModel.p0_dbm[node]`.
2. **Exponent and σ:** walk the tag over 20+ **surveyed test points**, fit `exponent` by least squares on (log10 d, RSSI), and set `sigma_db` to the residual standard deviation.
3. **Score it:** for each test point, build `GroundTruth(ts, "tag-01", x, y)` and call `evaluation.metrics.evaluate(result, truth, thresholds, elapsed_ms)`. Then feed the rows through `evaluation/aggregation.py` → error p50/p90, coverage of the 50%/90% regions, overconfident failures.
4. **Batch runs with the existing harness:** pass your own `trial_executor` to `experiments/validation_harness.run_batch(...)` that loads **recorded** observations instead of calling `simulation/synthetic.py`. It must return the same metrics dict that `run_experiment` returns.

Harness gotchas when you do this:
- `run_batch` only accepts scenario names from `experiments/baseline.SCENARIOS`. Use `"baseline"` as the label, or add a new runner that calls `summarize()` and `write_reports()` directly.
- `--replay` refuses manifests made with a custom executor ("must be replayed by their owning code"). Replay with your own script.
- `evaluate()` requires `result.timestamp == truth.timestamp` and matching emitter IDs. Stamp the truth with the same `evaluation_timestamp` you passed to the estimator.
- Real coverage numbers are what finally give meaning to the "CALIBRATION NOT ESTABLISHED" label. It only means something for **your site and your layout**.

---

## 9. What's NOT needed in live operation (keep it all in the repo)

| Part | Status | Why it's not needed live | Why keep it |
|---|---|---|---|
| `simulation/synthetic.py` | 💤 | Real RSSI replaces the random scalars | Tests; pipeline smoke checks without hardware |
| `localization/placeholder.py` | 💤 | Returns a fixed fixture that ignores measurements | Baseline and contract reference; tests assert it's unchanged |
| `experiments/baseline.py` (fault scenarios, `InvalidGridFixture`) | 🧪 | Injects synthetic faults | Failure-handling regression tests |
| `experiments/validation_harness.py` | 🧪 | Batch runs, not real-time | Calibration and accuracy campaigns (§8) |
| `models/ground_truth.py`, `evaluation/metrics.py::evaluate`, `evaluation/aggregation.py`, `evaluation/comparison.py` | 🧪 | No ground truth exists during live operation | Scoring calibration walks; comparing estimator versions |
| `visualization/plot.py`, `visualization/validation_plots.py` | 🧪 | Offline reports | Calibration reports; `plot.py` also shows how to draw model regions |
| `demo/` (scenario.py, player.py, mock_estimator.py, dashboard.py, scenarios/*.json) | 💤 | Positions are hand-written JSON; labels say SIMULATED | Presentations; rendering code to copy |
| `integrated/` (all files) | 💤 | Pairs authored map frames with synthetic telemetry; presentation only | Presentations; card UI to copy |
| `telemetry/engine.py` (`generate`, fault injection, `Engine`) | 💤 | Finite streams with fixed IDs; O(n²) | Testing health logic; the source of the rules in §6 |
| `telemetry/schema.py` | 💤 | Its 5-field schema requires `timestamp = seq × period` | Model for strict validation |
| `telemetry/dashboard.py`, `telemetry/__main__.py`, `telemetry/scenarios/*.json` | 💤 | Synthetic stream viewer | Demos; thresholds to copy |
| `main.py` modes `--demo`, `--integrated*`, `--monte-carlo`, `--report`, `--compare`, `--replay` | 💤 / 🧪 | Live service gets its own entry point (`live/run_live.py`) | Everything that exists today keeps working |
| `tests/` | 🧪 | Not deployed onto nodes or the server | CI; extend with `tests/test_rssi_estimator.py` |
| `outputs/`, `demo_*/`, `failure_demo/`, `replay_output/`, `comparison_output/`, `telemetry_output/`, `telemetry_examples/`, `phase3_examples/`, `phase3_preview/`, `run_outputs/` | 💤 | Generated artifacts | Historical evidence; examples |
| `*VALIDATION.md`, `*-output.json`, `test-results*.txt`, `phase3_validation/`, `telemetry_validation/` | 💤 | Historical records | Audit trail |
| GIF/PNG frame export (`export_demo`, `export_animation`) | 💤 | Live view doesn't need animations | Presentation exports |

### What IS needed live

| Part | Status |
|---|---|
| `models/receiver.py`, `models/observation.py`, `models/emitter.py` | ✅ reused as is |
| `config.py` → `EstimatorConfig` (with `evaluation_timestamp = now`) | ✅ reused as is |
| `localization/interface.py` → `Estimator`, `LocalizationResult`, `Status`, `validate_grid` | ✅ reused as is |
| `evaluation/metrics.py::model_region` (only to draw the 50%/90% regions) | ✅ reused as is |
| `localization/rssi_estimator.py` | ✅ **new** (§5) |
| `ingest/` (receiver + `RssiWindow`) | ✅ **new** (§4) |
| `NodeMonitor` (health rules from Phase 2) | ✅ **new** (§6) |
| `live/run_live.py` + live dashboard + recorder | ✅ **new** (§7) |
| Firmware on each node (scan → JSON → send) | ✅ **new**, outside this repo |
| `PathLossModel` calibration file (per site) | ✅ **new** (§8) |

---

## 10. Suggested build order

1. Write firmware that sends §4 messages; record 10 minutes of raw logs with the tag at known spots.
2. Add `localization/rssi_estimator.py` and `tests/test_rssi_estimator.py` (noise-free point → small error; fewer than 3 nodes → `INSUFFICIENT_DATA`; `"synthetic_unit"` → `INVALID_INPUT`; stale data → `STALE_DATA`).
3. Calibrate (§8) offline from the recorded logs, and check error and coverage.
4. Add ingest, `RssiWindow`, `NodeMonitor`, the live loop, and the dashboard.
5. Run live alongside the recorder; re-calibrate whenever nodes move or furniture changes.
6. Keep running `python -m unittest discover -s tests -v`. All 112 existing tests should still pass, because no existing file was edited.
