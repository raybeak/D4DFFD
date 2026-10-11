# Demo validation record

- Python 3.12.14; NumPy 2.3.5; Matplotlib 3.10.8; Pillow 12.3.0.
- `python -m unittest discover -s tests -v`: **56 passed, 0 failed**.
- All 42 pre-existing tests remain unchanged and passed.
- PlaceholderEstimator remains byte-identical, SHA-256:
  `f08cbd64318d01ad98c9e2e3675fe333825c8a0a252ec5ce2c90e25054cdbb3b`.
- All Phase 1.5 computational modules and original outputs remain byte-identical.
- Original files modified: main.py (demo dispatch/lazy imports), README.md.
- Three scenario commands completed: normal, uncertain, lost.
- Each scenario exported 31 PNGs and a GIF with 31 decodable frames.
- Total demonstration output: 93 PNGs, 3 GIFs, 3 replay manifests.
- All frames of all GIFs were reopened and decoded before packaging.
- Normal and lost screenshots were inspected for legibility and explicit mock labeling.
- Normal path and shrinking radius, uncertain path and constant wide radius, missing
  positions, loss/reacquisition states, reset, pause, speed, bounded history, and
  deterministic replay are covered by tests.
- Keyboard callbacks and render/export code were tested with a headless backend;
  a native desktop GUI window was not manually tested in this environment.
- A zero-byte GIF detected during output inspection was regenerated. Export now writes
  to a temporary file, validates all GIF frames, then replaces the final destination.
- Legacy single-scenario command passed using a separate output directory.
- A fresh 100-trial validation batch and its manifest replay passed; all deterministic
  metrics matched with timing fields excluded. Report and comparison commands passed.
- Existing 1.5 manifests fingerprint the old release and intentionally require that
  release for exact replay. New manifests work with this release; checks were not weakened.
- No measurement-based localization, motion prediction, RF model, hardware interface,
  tracking algorithm, or subsequent phase was implemented.
