"""Replay and UI contract tests; no physical localization assertions."""
from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from types import SimpleNamespace
from dataclasses import replace
import numpy as np
from demo.scenario import builtin_scenario, load_scenario
from demo.mock_estimator import MockEstimator
from demo.player import DemoPlayer


class DemoTests(unittest.TestCase):
    def test_json_scenarios(self):
        for name in ("normal", "uncertain", "lost"):
            s = builtin_scenario(name)
            self.assertEqual(s.frames[0].time, 0)
            self.assertEqual(s.frames[-1].time, 30)
            self.assertEqual(len(s.frames), 31)

    def test_mock_returns_exact_authored_positions(self):
        s = builtin_scenario("normal")
        mock = MockEstimator(s)
        for i, frame in enumerate(s.frames):
            self.assertEqual(mock.estimate(i).representative_position, frame.position)

    def test_mock_ignores_observations(self):
        mock = MockEstimator(builtin_scenario("normal"))
        a = mock.estimate(3, observations=[1, 2, 3])
        b = mock.estimate(3, observations=[float("nan"), -999])
        np.testing.assert_array_equal(a.probability_grid, b.probability_grid)
        self.assertEqual(a.representative_position, b.representative_position)

    def test_blob_valid_and_scripted_size_changes(self):
        mock = MockEstimator(builtin_scenario("normal"))
        for i in (0, 15, 30):
            p = mock.estimate(i).probability_grid
            self.assertTrue(np.isfinite(p).all())
            self.assertTrue((p >= 0).all())
            self.assertAlmostEqual(float(p.sum()), 1)
        self.assertNotEqual(float(mock.estimate(0).probability_grid.max()), float(mock.estimate(30).probability_grid.max()))

    def test_history_is_bounded_and_past_only(self):
        p = DemoPlayer(builtin_scenario("normal"), history_length=10)
        p.play()
        for _ in range(60):
            p.advance(.5)
            self.assertLessEqual(len(p.history), 10)
            self.assertTrue(all(f.time <= p.elapsed for f in p.history))
        self.assertEqual(len(p.history), 10)

    def test_missing_data_produces_no_position(self):
        s = builtin_scenario("lost")
        mock = MockEstimator(s)
        for i in range(8, 17):
            result = mock.estimate(i)
            self.assertIsNone(result.representative_position)
            self.assertIsNone(result.probability_grid)
        self.assertEqual(s.frames[8].track_status, "DEGRADED")
        self.assertEqual(s.frames[10].track_status, "LOST")
        self.assertEqual(s.frames[17].track_status, "REACQUIRING")
        self.assertEqual(s.frames[19].track_status, "TRACKING")

    def test_reset_first_frame(self):
        p = DemoPlayer(builtin_scenario("normal"))
        p.play(); p.advance(20); p.reset()
        self.assertEqual(p.frame_index, 0)
        self.assertEqual(p.elapsed, 0)
        self.assertEqual(len(p.history), 1)
        self.assertFalse(p.playing)

    def test_replay_deterministic(self):
        traces = []
        for _ in range(2):
            p = DemoPlayer(builtin_scenario("lost"), speed=2)
            p.play()
            trace = []
            for dt in (.1, .4, 1, 3, 5, .2, 4, 8):
                p.advance(dt)
                trace.append((p.elapsed, p.frame_index, p.current_frame, tuple(p.history)))
            traces.append(trace)
        self.assertEqual(traces[0], traces[1])

    def test_play_pause_speed_and_end(self):
        p = DemoPlayer(builtin_scenario("normal"), speed=.5)
        p.play(); p.advance(2)
        self.assertEqual(p.elapsed, 1)
        p.pause(); p.advance(10)
        self.assertEqual(p.elapsed, 1)
        p.set_speed(2); p.play(); p.advance(100)
        self.assertEqual(p.elapsed, 30)
        self.assertFalse(p.playing)

    def test_no_interpolation_between_authored_frames(self):
        p = DemoPlayer(builtin_scenario("normal"))
        p.seek(1.8)
        self.assertEqual(p.current_frame.position, (22., 21.))

    def test_malformed_scenarios_rejected(self):
        base = json.loads((Path(__file__).parents[1]/"demo/scenarios/normal.json").read_text())
        edits = [lambda d: d.update(frames=[]),
                 lambda d: d["frames"][0].update(position=[101,20]),
                 lambda d: d["frames"][0].update(uncertainty_radius=0),
                 lambda d: d["frames"][0].update(track_status="LOST"),
                 lambda d: d["frames"][1].update(time=0),
                 lambda d: d["frames"][0].update(position=None),
                 lambda d: d.update(duration_seconds=float("nan")),
                 lambda d: d.update(data_source="MEASURED")]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"scenario.json"
            for edit in edits:
                data = json.loads(json.dumps(base))
                edit(data)
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    load_scenario(path)
            path.write_text("not json")
            with self.assertRaises(ValueError):
                load_scenario(path)

    def test_placeholder_unchanged(self):
        path = Path(__file__).parents[1]/"localization/placeholder.py"
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         "f08cbd64318d01ad98c9e2e3675fe333825c8a0a252ec5ce2c90e25054cdbb3b")

    def test_dashboard_gap_and_controls(self):
        import matplotlib
        matplotlib.use("Agg")
        from demo.dashboard import DemoDashboard
        p = DemoPlayer(builtin_scenario("lost"))
        ui = DemoDashboard(p)
        try:
            ui.keypress(SimpleNamespace(key=" "))
            self.assertTrue(p.playing)
            p.seek(10); ui.render()
            self.assertFalse(ui.marker.get_visible())
            self.assertFalse(ui.ring.get_visible())
            self.assertFalse(ui.blob.get_visible())
            self.assertTrue(ui.gap.get_visible())
            self.assertIsNone(p.current_frame.position)
            self.assertTrue(np.isnan(ui.tail.get_xdata()).any())
            ui.keypress(SimpleNamespace(key="3"))
            self.assertEqual(p.speed, 2)
            ui.keypress(SimpleNamespace(key="r"))
            self.assertEqual(p.frame_index, 0)
            self.assertTrue(ui.marker.get_visible())
        finally:
            ui.plt.close(ui.fig)

    def test_export_gif_and_state_restore(self):
        import matplotlib
        matplotlib.use("Agg")
        from PIL import Image
        from demo.dashboard import DemoDashboard, export_demo
        scenario = builtin_scenario("normal")
        scenario = replace(scenario, frames=scenario.frames[:2], duration_seconds=1.)
        player = DemoPlayer(scenario, speed=2)
        player.play()
        ui = DemoDashboard(player)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                export_demo(ui, Path(tmp), "both")
                with Image.open(Path(tmp)/"animation.gif") as gif:
                    self.assertEqual(gif.n_frames, 2)
                    self.assertEqual(gif.info["duration"], 500)
                self.assertEqual(len(list(Path(tmp).glob("frame_*.png"))), 2)
                self.assertTrue((Path(tmp)/"replay_manifest.json").is_file())
            self.assertTrue(player.playing)
            self.assertEqual(player.frame_index, 0)
            self.assertFalse(ui.exporting)
        finally:
            ui.plt.close(ui.fig)
