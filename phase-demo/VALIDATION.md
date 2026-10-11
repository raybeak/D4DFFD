# Phase 1.5 validation record

- Runtime: Python 3.12.14; NumPy 2.3.5; Matplotlib 3.10.8.
- Total automated tests: **42 passed, 0 failed** (23 original + 19 added).
- All original test files are byte-for-byte unchanged.
- PlaceholderEstimator is byte-for-byte unchanged; SHA-256:
  `f08cbd64318d01ad98c9e2e3675fe333825c8a0a252ec5ce2c90e25054cdbb3b`.
- Default `python main.py` still runs and generates the Phase 1 baseline image.
- 100 baseline trials, seeds 42–141: 100 valid, 0 failed.
- Median error and p90 error: 33.421549934136806 m (fixed fixture, not RF accuracy).
- Median region areas: 448 m² (50%), 1472 m² (90%).
- Empirical inclusion: 0% for both regions; overconfident failures: 100.
- Tiny nonzero standard deviation (~7.1e-15 m) is floating-point summation noise.
- Manifest replay of all 100 trials reproduced every deterministic trial metric exactly;
  measured processing times were excluded from equality.
- Report regeneration from saved CSV and BASELINE/CANDIDATE comparison commands passed.
- Additional 12-scenario batch, 5 trials each: 60 attempted, 19 valid, 41 failed.
  This exercises dropout, stale, insufficient data, invalid input, and invalid grid states.
- Empty/all-failed report image generation is covered by tests.
- Baseline coverage and uncertainty-area figures inspected for readable labels and warnings.
- New localization algorithms: none. Phase 2/3 functionality: none.

## Original Phase 1 validation record

- Runtime: Python 3.12.14; NumPy 2.3.5; Matplotlib 3.10.8.
- `python main.py`: passed; metrics printed and baseline image generated.
- `python main.py --scenario all`: passed; all 12 scenario outputs generated.
- `python -m unittest discover -s tests -v`: 23 tests passed, 0 failed.
- Reproducibility tests run all 12 scenarios twice, compare observation bytes and
  deterministic metrics, excluding measured processing time.
- Truth isolation: restricted-config spy, static dependency/access checks, and
  changed-truth invariance test passed.
- Baseline image inspected for readable labels, cell-mass display, both region
  contours, synthetic truth, receiver markers, and placeholder warnings.
- Float cumulative-mass boundary issue found by a test was fixed before delivery.
- Results validate the software pipeline only; no measured hardware results exist.
