# Phase 2 validation report

Executed 2026-10-10. Environment: Python 3.12.14, NumPy 2.3.5,
Matplotlib 3.10.8, Linux, Agg headless backend. Python 3.11 is the supported
minimum by syntax/API usage; no separate Python 3.11 interpreter run was performed.

## Actual results

| Validation | Result |
| --- | --- |
| Existing suite before code modifications | 56 tests, 1.632s, OK |
| Complete suite after final code modifications | 83 tests, 1.773s, OK |
| New telemetry tests within complete suite | 27 passed |
| Normal scenario command | Exit 0; JSON, CSV and PNG generated |
| Mixed faults scenario command | Exit 0; all five fault categories exercised |
| Outage/recovery scenario command | Exit 0; states tested separately at explicit times |
| Recorded mixed-fault replay command | Exit 0 |
| Replay equivalence | report.json, report.csv, recording.json, messages.csv byte-identical |
| Dashboard | Repeated updates tested, no table/line artist growth, PNG visually inspected |
| Original archive preservation | Every original file byte-identical except appended README.md |
| Dependency isolation | AST test verifies no imports of earlier-phase modules in telemetry |

Full raw test outputs: `telemetry_validation/baseline-tests.txt` and
`telemetry_validation/all-tests.txt`. No test failures occurred during implementation.

## Preserved estimators

SHA-256 matches the original uploaded archive:

- `localization/placeholder.py`: `f08cbd64318d01ad98c9e2e3675fe333825c8a0a252ec5ce2c90e25054cdbb3b`
- `demo/mock_estimator.py`: `9c919ea24e442a843548fc493542b4dfcbe719a91c5cc3ed4e71860753244fb0`

The original main.py, requirements, all existing modules, tests, demo scenarios
and prior outputs are preserved. Telemetry has its own entry point and no data
connection to existing estimators.

## New test coverage

Strict schema/types; nonfinite and malformed measurements; configuration errors;
four stream generation; seed determinism; stream independence; initial/middle/final
missing packets; total silence; duplicate suppression; delayed/out-of-order arrival;
late gap reconciliation; latest-value ordering; invalid quality and range;
unknown sensor rejection; future timestamp and excessive sequence rejection;
HEALTHY/DEGRADED/OFFLINE/RECOVERING transitions; duplicate liveness protection;
rate-window boundaries; inclusive delay threshold; latency statistics; step-size
independent replay; reset/seek; recording validation; CSV/JSON round trip;
input immutability; built-in scenarios; dashboard rendering; dependency isolation.

## Exact commands used

From the extracted `phase-demo` directory:

```bash
MPLBACKEND=Agg python -m unittest discover -s tests -v
python -m telemetry --scenario telemetry/scenarios/mixed_faults.json --headless --output-dir telemetry_examples/mixed_faults
python -m telemetry --replay telemetry_examples/mixed_faults/recording.json --headless --output-dir telemetry_examples/replay
python -m telemetry --scenario telemetry/scenarios/normal.json --headless --output-dir telemetry_examples/normal
python -m telemetry --scenario telemetry/scenarios/outage_recovery.json --headless --output-dir telemetry_examples/outage_recovery
```

The complete suite command was executed before implementation and again after
implementation. Output folders above are included. README contains installation,
live dashboard, custom seed, dedicated test and replay execution commands.

## Limitations

The graphical window was not manually operated in this headless environment.
Dashboard updates and rendering were actually executed using Agg. No claim of GUI
backend verification or multi-platform testing is made. Playback is real-time-paced
synthetic data, not an external hardware or network receiver. The finite engine
retains full recording/monitor histories in memory. Its schedule-based loss metric
requires the declared synthetic start time, period and sample count. Historical
loss and error counts persist after current health recovers. RNG regeneration is
version-dependent; exact recorded-message replay avoids that dependency.

## Deliverable contents

- Existing project with README Phase 2 section appended.
- New telemetry source package and three scenario JSON files.
- New automated test module (27 tests).
- This report and both test logs.
- Executed normal, mixed faults, outage/recovery, and replay examples.

Only Phase 2 was implemented. No additional phase was started.
