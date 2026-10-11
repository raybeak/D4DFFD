"""Independent telemetry contracts, fault handling, replay and exports."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from telemetry.schema import Message
from telemetry.engine import Engine, IDS, generate, save_recording, load_recording


def config(**updates):
    c = dict(seed=42, samples=12, period=1., delay_limit=.5, offline_after=2.5, recovery_messages=3, faults={})
    c.update(updates)
    return c


def run(c):
    r = generate(c)
    e = Engine(r)
    e.advance(r['end_time'])
    return e


class TelemetryTests(unittest.TestCase):
    def test_message_roundtrip(self):
        m = Message('sensor-1', 0., 0, 1., 'GOOD')
        self.assertEqual(Message.parse(m.to_dict()), m)

    def test_strict_schema(self):
        raw = Message('sensor-1', 0., 0, 1., 'GOOD').to_dict()
        bad = [('timestamp', True), ('timestamp', -1), ('timestamp', float('inf')), ('sequence_number', True), ('sequence_number', 1.2), ('measurement_value', float('nan')), ('measurement_value', '1'), ('quality_flag', 'unknown'), ('sensor_id', '')]
        for key, value in bad:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                Message.parse(dict(raw, **{key:value}))
        with self.assertRaises(ValueError):
            Message.parse(dict(raw, extra=1))
        del raw['quality_flag']
        with self.assertRaises(ValueError):
            Message.parse(raw)

    def test_config_rejections(self):
        for update in [dict(seed=-1), dict(samples=True), dict(period=0), dict(delay_limit=float('nan')), dict(offline_after=.1), dict(recovery_messages=0), dict(faults={'no':{}}), dict(faults={'sensor-1':{'drop':[99]}}), dict(faults={'sensor-1':{'delay':{'2':-1}}})]:
            with self.subTest(update=update), self.assertRaises(ValueError):
                generate(config(**update))

    def test_four_streams_normal(self):
        e = run(config())
        rows = e.snapshot()['sensors']
        self.assertEqual([r['sensor_id'] for r in rows], list(IDS))
        self.assertTrue(all(r['state']=='HEALTHY' and r['error_count']==0 and r['received_unique']==12 for r in rows))

    def test_seed_reproducibility(self):
        self.assertEqual(generate(config()), generate(config()))
        self.assertNotEqual(generate(config(seed=1))['events'], generate(config(seed=2))['events'])

    def test_stream_independence(self):
        a = generate(config())
        b = generate(config(faults={'sensor-1':{'drop':[1,2], 'duplicate':[3]}}))
        for sid in IDS[1:]:
            self.assertEqual([e for e in a['events'] if e['message']['sensor_id']==sid], [e for e in b['events'] if e['message']['sensor_id']==sid])

    def test_missing_initial_middle_final(self):
        e = run(config(faults={'sensor-1':{'drop':[0,5,11]}}))
        r = e.snapshot()['sensors'][0]
        self.assertEqual(r['missing_messages'], 3)
        self.assertEqual(r['packet_loss'], .25)

    def test_duplicate_not_counted_as_unique(self):
        e = run(config(faults={'sensor-1':{'duplicate':[2]}}))
        r = e.snapshot()['sensors'][0]
        self.assertEqual(r['duplicate_errors'], 1)
        self.assertEqual(r['received_unique'], 12)
        self.assertEqual(len(e.sensors['sensor-1'].history), 12)

    def test_delay_reconciles_loss(self):
        e = Engine(generate(config(faults={'sensor-1':{'delay':{'1':3.}}})))
        e.advance(2.)
        self.assertEqual(e.snapshot()['sensors'][0]['missing_messages'], 1)
        e.advance(4.)
        r = e.snapshot()['sensors'][0]
        self.assertEqual(r['missing_messages'], 0)
        self.assertEqual(r['delayed_errors'], 1)
        self.assertEqual(r['out_of_order_errors'], 1)
        self.assertEqual(e.sensors['sensor-1'].latest_sequence, 4)

    def test_invalid_quality_does_not_replace_latest(self):
        e = run(config(faults={'sensor-1':{'invalid':[11]}}))
        self.assertEqual(e.sensors['sensor-1'].latest_sequence, 10)
        r = e.snapshot()['sensors'][0]
        self.assertEqual(r['invalid_errors'], 1)
        self.assertEqual(r['missing_messages'], 0)

    def test_range_invalid(self):
        r = generate(config())
        r['events'][0]['message']['measurement_value'] = 101.
        e = Engine(r)
        e.advance(0)
        self.assertIsNone(e.snapshot()['sensors'][0]['latest_measurement'])
        self.assertEqual(e.snapshot()['sensors'][0]['invalid_errors'], 1)

    def test_malformed_and_unknown(self):
        r = generate(config())
        del r['events'][0]['message']['quality_flag']
        r['events'][1]['message']['sensor_id'] = []
        e = Engine(r)
        e.advance(0)
        self.assertEqual(e.snapshot()['rejected_unknown'], 1)
        self.assertEqual(e.snapshot()['sensors'][0]['invalid_errors'], 1)

    def test_future_timestamp_and_unbounded_sequence(self):
        for key, value in [('timestamp', 99), ('sequence_number', 10**12)]:
            r = generate(config())
            r['events'][0]['message'][key] = value
            e = Engine(r)
            e.advance(0)
            self.assertEqual(e.snapshot()['sensors'][0]['invalid_errors'], 1)

    def test_health_outage_recovery(self):
        e = Engine(generate(config(faults={'sensor-1':{'drop':[3,4,5,6]}})))
        self.assertEqual(e.advance(0)['sensors'][0]['state'], 'RECOVERING')
        self.assertEqual(e.advance(2)['sensors'][0]['state'], 'HEALTHY')
        self.assertEqual(e.advance(3.5)['sensors'][0]['state'], 'DEGRADED')
        self.assertEqual(e.advance(5)['sensors'][0]['state'], 'OFFLINE')
        self.assertEqual(e.advance(7)['sensors'][0]['state'], 'RECOVERING')
        self.assertEqual(e.advance(9)['sensors'][0]['state'], 'HEALTHY')

    def test_completely_silent_sensor(self):
        e = run(config(faults={'sensor-1':{'drop':list(range(12))}}))
        r = e.snapshot()['sensors'][0]
        self.assertEqual(r['state'], 'OFFLINE')
        self.assertEqual(r['packet_loss'], 1.)
        self.assertIsNone(r['latency_mean_seconds'])

    def test_rate_window_and_duplicate_exclusion(self):
        e = Engine(generate(config(faults={'sensor-1':{'duplicate':[0]}})))
        self.assertEqual(e.advance(0)['sensors'][0]['message_rate_hz'], 1)
        self.assertEqual(e.advance(1)['sensors'][0]['message_rate_hz'], 1)
        e.recording['end_time'] = 20
        self.assertEqual(e.advance(20)['sensors'][0]['message_rate_hz'], 0)

    def test_exact_delay_threshold(self):
        e = run(config(faults={'sensor-1':{'delay':{'1':.5}}}))
        r = e.snapshot()['sensors'][0]
        self.assertEqual(r['delayed_errors'], 1)
        self.assertEqual(r['missing_messages'], 0)

    def test_duplicate_does_not_revive_offline(self):
        r = generate(config(faults={'sensor-1':{'drop':list(range(1,12))}}))
        duplicate = copy.deepcopy(r['events'][0])
        duplicate['arrival_time'] = 8.
        r['events'].append(duplicate)
        r['events'].sort(key=lambda e: e['arrival_time'])
        e = Engine(r)
        self.assertEqual(e.advance(8.)['sensors'][0]['state'], 'OFFLINE')

    def test_latency_mean(self):
        e = run(config(faults={'sensor-1':{'delay':{'1':3.}}}))
        self.assertAlmostEqual(e.snapshot()['sensors'][0]['latency_mean_seconds'], .25)

    def test_replay_step_size_independent(self):
        r = generate(config(faults={'sensor-1':{'drop':[0,4,11], 'delay':{'1':2.2}, 'invalid':[6], 'duplicate':[8]}}))
        direct = Engine(r)
        expected = direct.advance(r['end_time'])
        stepped = Engine(r)
        for t in np.linspace(0, r['end_time'], 213):
            stepped.advance(float(t))
        self.assertEqual(expected, stepped.snapshot())
        self.assertEqual(expected, stepped.seek(r['end_time']))

    def test_seek_reset(self):
        e = run(config())
        self.assertEqual(e.seek(0), Engine(generate(config())).advance(0))
        with self.assertRaises(ValueError):
            e.advance(-1)
        with self.assertRaises(ValueError):
            e.seek(float('nan'))

    def test_recording_validation(self):
        r = generate(config())
        for mutation in ['order', 'end', 'arrival', 'version']:
            bad = copy.deepcopy(r)
            if mutation == 'order': bad['events'].reverse()
            if mutation == 'end': bad['end_time'] = 0
            if mutation == 'arrival': bad['events'][0]['arrival_time'] = float('nan')
            if mutation == 'version': bad['version'] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                Engine(bad)

    def test_json_replay_and_export(self):
        e = run(config())
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            save_recording(e.recording, p/'recording.json')
            replay = Engine(load_recording(p/'recording.json'))
            self.assertEqual(replay.advance(e.now), e.snapshot())
            e.export(p)
            self.assertEqual(json.loads((p/'report.json').read_text()), e.snapshot())
            with (p/'report.csv').open() as f:
                self.assertEqual(len(list(csv.DictReader(f))), 4)
            with (p/'messages.csv').open() as f:
                self.assertEqual(len(list(csv.DictReader(f))), 48)

    def test_no_input_mutation(self):
        c = config()
        r = generate(c)
        original = copy.deepcopy(r)
        e = Engine(r)
        e.advance(r['end_time'])
        self.assertEqual(r, original)
        self.assertEqual(c, config())

    def test_builtin_scenarios(self):
        for path in Path('telemetry/scenarios').glob('*.json'):
            e = run(json.loads(path.read_text()))
            self.assertEqual(len(e.snapshot()['sensors']), 4)

    def test_dashboard_updates_without_artist_growth(self):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from telemetry.dashboard import Dashboard
        d = Dashboard(generate(config()))
        for t in (0, 2, 5):
            d.update(t)
        self.assertEqual(len(d.status.tables), 1)
        self.assertEqual(len(d.plot.lines), 4)
        with tempfile.TemporaryDirectory() as tmp:
            d.save(Path(tmp)/'dashboard.png')
            self.assertGreater((Path(tmp)/'dashboard.png').stat().st_size, 1000)
        plt.close(d.figure)

    def test_no_legacy_dependencies(self):
        import ast
        for path in Path('telemetry').glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                modules = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ''] if isinstance(node, ast.ImportFrom) and node.level == 0 else []
                self.assertFalse(any(m.split('.')[0] in {'localization','demo','simulation','experiments','evaluation','models'} for m in modules))
