"""Shared-clock and UI contracts; map positions remain authored fixtures."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import matplotlib
matplotlib.use('Agg')
from integrated.controller import Controller
from integrated.dashboard import IntegratedDashboard
from integrated.reporting import export_reports, export_animation, load_manifest
from telemetry.engine import Engine, generate


class IntegratedTests(unittest.TestCase):
    def test_shared_clock(self):
        c=Controller()
        c.play()
        c.advance(3.25)
        self.assertEqual(c.clock.time,c.player.elapsed)
        self.assertEqual(c.clock.time,c.telemetry.now)
        self.assertEqual(c.player.current_frame.time,3)

    def test_pause(self):
        c=Controller()
        c.play(); c.advance(3); c.pause()
        before=c.snapshot()
        c.advance(10)
        self.assertEqual(before,c.snapshot())

    def test_reset(self):
        c=Controller('uncertain')
        initial=c.snapshot()
        c.play(); c.advance(20); c.reset()
        self.assertEqual(initial,c.snapshot())
        self.assertFalse(c.clock.playing)

    def test_speeds(self):
        for speed in (.5,1.,2.):
            c=Controller(speed=speed)
            c.play(); c.advance(2)
            self.assertEqual(c.clock.time,2*speed)
        for speed in (0,3,True,float('nan')):
            with self.assertRaises(ValueError): c.set_speed(speed)

    def test_seek_no_future_state(self):
        c=Controller('uncertain')
        c.seek(29); actual=c.seek(4)
        fresh=Controller('uncertain')
        self.assertEqual(actual,fresh.seek(4))
        self.assertTrue(all(f.time<=4 for f in c.player.history))
        self.assertTrue(all(t<=4 for s in c.telemetry.sensors.values() for t in s.arrivals))

    def test_seek_reproducibility(self):
        c=Controller('lost')
        expected=c.seek(12)
        c.seek(29)
        self.assertEqual(expected,c.seek(12))

    def test_switch_resets(self):
        c=Controller('normal',seed=8,speed=2)
        c.seek(20); c.switch('lost')
        self.assertEqual(c.snapshot(),Controller('lost',seed=8,speed=2).snapshot())
        self.assertEqual(c.clock.speed,2)
        self.assertFalse(c.clock.playing)

    def test_invalid_switch_is_atomic(self):
        c=Controller(); c.seek(4)
        before=c.snapshot()
        with self.assertRaises(ValueError): c.switch('no')
        self.assertEqual(before,c.snapshot())

    def test_health_is_engine_output(self):
        c=Controller('lost')
        direct=Engine(c.telemetry.recording)
        for t in (0,5,8,10,12,30.75):
            actual=c.seek(t)['telemetry']['sensors']
            expected=direct.seek(t)['sensors']
            for a,b in zip(actual,expected):
                for key,value in b.items(): self.assertEqual(a[key],value)

    def test_telemetry_changes_cannot_change_map(self):
        c=Controller('uncertain')
        r=copy.deepcopy(c.telemetry.recording)
        for e in r['events']: e['message']['measurement_value']=-50.
        changed=Controller.from_payload(c.name,c.demo_data,r)
        for t in (0,3,12,20,30):
            self.assertEqual(c.seek(t)['map_frame'],changed.seek(t)['map_frame'])

    def test_no_estimator_calls_in_controller(self):
        import integrated.controller as module
        source=Path(module.__file__).read_text()
        self.assertNotIn('Estimator',source)
        tree=ast.parse(Path('integrated/dashboard.py').read_text())
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='estimate']
        self.assertEqual(len(calls),1)
        self.assertEqual(len(calls[0].args),1)
        self.assertEqual(calls[0].keywords,[])

    def test_lost_no_fabricated_position(self):
        c=Controller('lost')
        c.seek(12)
        self.assertIsNone(c.snapshot()['map_frame']['position'])
        d=IntegratedDashboard(c)
        try:
            self.assertFalse(d.marker.get_visible())
            self.assertFalse(d.ring.get_visible())
            self.assertFalse(d.blob.get_visible())
            self.assertEqual(len(d.marker.get_xdata()),0)
        finally: d.plt.close(d.fig)

    def test_ui_callbacks(self):
        d=IntegratedDashboard(Controller())
        try:
            d.play(); self.assertTrue(d.controller.clock.playing)
            d.controller.advance(2)
            d.pause(); self.assertFalse(d.controller.clock.playing)
            d.set_speed(.5); self.assertEqual(d.controller.clock.speed,.5)
            d.slider.set_val(5); self.assertEqual(d.controller.clock.time,5)
            d.reset(); self.assertEqual(d.controller.clock.time,0)
            d.switch('lost'); self.assertEqual(d.controller.name,'lost')
            before=len(d.fig.axes)
            for t in (2,4,8): d.seek(t)
            self.assertEqual(len(d.fig.axes),before)
        finally: d.plt.close(d.fig)

    def test_timer_uses_controller_clock(self):
        d=IntegratedDashboard(Controller())
        try:
            d.controller.play(); d.last_tick=10
            with patch('integrated.dashboard.time.perf_counter',return_value=11): d.tick()
            self.assertEqual(d.controller.clock.time,1)
        finally: d.plt.close(d.fig)

    def test_manifest_round_trip(self):
        c=Controller('uncertain',seed=8,speed=2)
        c.seek(6); c.play()
        with tempfile.TemporaryDirectory() as tmp:
            export_reports(c,tmp)
            replay=load_manifest(Path(tmp)/'replay_manifest.json')
            self.assertEqual(replay.snapshot(),c.snapshot())
            self.assertEqual(replay.clock.playing,c.clock.playing)
            self.assertEqual(replay.clock.speed,2)
            replay.advance(1); c.advance(1)
            self.assertEqual(replay.snapshot(),c.snapshot())
            import csv
            with (Path(tmp)/'telemetry_summary.csv').open() as f:
                self.assertEqual(len(list(csv.DictReader(f))),4)

    def test_export_frames_gif_and_restore(self):
        source=Controller()
        data=copy.deepcopy(source.demo_data)
        data['duration_seconds']=1.
        data['frames']=data['frames'][:2]
        config=copy.deepcopy(source.telemetry.config)
        config['samples']=1
        c=Controller.from_payload('normal',data,generate(config))
        d=IntegratedDashboard(c)
        c.seek(.5); c.play()
        before=c.snapshot()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                export_animation(d,tmp,'both')
                self.assertEqual(len(list(Path(tmp).glob('frame_*.png'))),3)
                from PIL import Image
                with Image.open(Path(tmp)/'animation.gif') as gif:
                    self.assertEqual(gif.n_frames,3)
                    for i in range(gif.n_frames): gif.seek(i); gif.load()
                replay=load_manifest(Path(tmp)/'replay_manifest.json')
                self.assertEqual(replay.clock.duration,1.)
                self.assertEqual(replay.clock.time,1.)
            self.assertEqual(before,c.snapshot())
            self.assertTrue(c.clock.playing)
        finally: d.plt.close(d.fig)

    def test_invalid_pairing(self):
        with self.assertRaisesRegex(ValueError,'pairing'): Controller('bad')

    def test_missing_telemetry_file(self):
        with self.assertRaisesRegex(ValueError,'Cannot load integrated pairing'):
            Controller(telemetry_path=Path('/no/such/configuration.json'))

    def test_malformed_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.json'; p.write_text('{')
            with self.assertRaisesRegex(ValueError,'Cannot load integrated pairing'): Controller(demo_path=p)
            with self.assertRaisesRegex(ValueError,'Cannot load integrated replay'): load_manifest(p)

    def test_invalid_timestamps(self):
        c=Controller()
        bad=copy.deepcopy(c.demo_data)
        bad['frames'][1]['time']=-1
        with self.assertRaises(ValueError): Controller.from_payload('normal',bad,c.telemetry.recording)
        r=copy.deepcopy(c.telemetry.recording); r['events'][0]['arrival_time']=-1
        with self.assertRaises(ValueError): Controller.from_payload('normal',c.demo_data,r)

    def test_empty_telemetry(self):
        c=Controller(); r=copy.deepcopy(c.telemetry.recording); r['events']=[]
        empty=Controller.from_payload('normal',c.demo_data,r)
        rows=empty.seek(10)['telemetry']['sensors']
        self.assertTrue(all(row['state']=='OFFLINE' and row['latest_measurement'] is None for row in rows))
        self.assertEqual(empty.player.current_frame.position,c.player.scenario.frames[10].position)

    def test_invalid_seek_and_elapsed(self):
        c=Controller()
        for value in (-1,100,float('nan'),True):
            with self.assertRaises(ValueError): c.seek(value)
        for value in (-1,float('inf'),True):
            with self.assertRaises(ValueError): c.advance(value)

    def test_complete_duration_and_hold(self):
        c=Controller(); c.play(); c.advance(100)
        self.assertEqual(c.clock.time,30.75)
        self.assertEqual(c.telemetry.now,30.75)
        self.assertEqual(c.player.elapsed,30)
        self.assertTrue(c.snapshot()['map_held_at_end'])
        self.assertFalse(c.clock.playing)

    def test_raw_data_unmodified(self):
        c=Controller('uncertain'); original=copy.deepcopy(c.telemetry.recording)
        for t in (10,2,30): c.seek(t)
        self.assertEqual(c.telemetry.recording,original)

    def test_last_message_metadata_by_sensor(self):
        c=Controller(); rows=c.seek(3)['telemetry']['sensors']
        for i,row in enumerate(rows):
            self.assertEqual(row['sensor_id'],f'sensor-{i+1}')
            self.assertEqual(row['last_message_timestamp'],3)
            self.assertEqual(row['last_sequence_number'],6)

    def test_step_size_independent(self):
        c=Controller('uncertain'); d=Controller('uncertain')
        c.play(); d.play(); c.advance(10)
        for _ in range(40): d.advance(.25)
        self.assertEqual(c.snapshot(),d.snapshot())

    def test_placeholder_unchanged(self):
        self.assertEqual(hashlib.sha256(Path('localization/placeholder.py').read_bytes()).hexdigest(),'f08cbd64318d01ad98c9e2e3675fe333825c8a0a252ec5ce2c90e25054cdbb3b')

    def test_mock_unchanged(self):
        self.assertEqual(hashlib.sha256(Path('demo/mock_estimator.py').read_bytes()).hexdigest(),'9c919ea24e442a843548fc493542b4dfcbe719a91c5cc3ed4e71860753244fb0')

    def test_missing_optional_dependency(self):
        import builtins
        real_import=builtins.__import__
        def missing(name,*args,**kwargs):
            if name=='PIL': raise ImportError('test missing Pillow')
            return real_import(name,*args,**kwargs)
        d=IntegratedDashboard(Controller())
        try:
            with patch('builtins.__import__',side_effect=missing):
                with self.assertRaisesRegex(ValueError,'Pillow'): export_animation(d,'unused-output','gif')
        finally: d.plt.close(d.fig)
