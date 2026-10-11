"""Seeded streams, transport fault injection, monitoring and virtual-clock replay."""
import copy
import csv
import json
import math
from pathlib import Path
import numpy as np
from .schema import Message, Health, number

IDS = tuple(f'sensor-{i}' for i in range(1, 5))
ERRORS = ('duplicate', 'delayed', 'out_of_order', 'invalid')


def validate_config(c):
    keys = {'seed', 'samples', 'period', 'delay_limit', 'offline_after', 'recovery_messages', 'faults'}
    if type(c) is not dict or set(c) != keys:
        raise ValueError('invalid configuration fields')
    for key, minimum in [('seed', 0), ('samples', 1), ('recovery_messages', 1)]:
        if type(c[key]) is not int or c[key] < minimum:
            raise ValueError(f'{key} must be an integer >= {minimum}')
    for key in ('period', 'delay_limit', 'offline_after'):
        if not number(c[key]) or c[key] <= 0:
            raise ValueError(f'{key} must be positive and finite')
    if c['offline_after'] <= c['delay_limit']:
        raise ValueError('offline_after must exceed delay_limit')
    if type(c['faults']) is not dict or not set(c['faults']) <= set(IDS):
        raise ValueError('unknown sensor in faults')
    for faults in c['faults'].values():
        if type(faults) is not dict or not set(faults) <= {'drop', 'duplicate', 'invalid', 'delay'}:
            raise ValueError('unknown fault')
        for kind, items in faults.items():
            if kind == 'delay':
                if type(items) is not dict:
                    raise ValueError('delay must map sequence strings to seconds')
                for seq, delay in items.items():
                    if not isinstance(seq, str) or not seq.isdigit() or str(int(seq)) != seq or not 0 <= int(seq) < c['samples'] or not number(delay) or delay < 0:
                        raise ValueError('invalid delay entry')
            elif type(items) is not list or any(type(i) is not int or not 0 <= i < c['samples'] for i in items):
                raise ValueError('fault sequences outside scheduled range')
    return copy.deepcopy(c)


def generate(config):
    c = validate_config(config)
    events = []
    for index, sensor in enumerate(IDS):
        # Independent RNG per sensor: faults never consume random draws.
        rng = np.random.default_rng(np.random.SeedSequence([c['seed'], index]))
        values = rng.normal(index * 10, 1, c['samples'])
        f = c['faults'].get(sensor, {})
        for seq, value in enumerate(values):
            if seq in f.get('drop', []):
                continue
            stamp = seq * c['period']
            message = Message(sensor, stamp, seq, float(value), 'BAD' if seq in f.get('invalid', []) else 'GOOD')
            arrival = stamp + f.get('delay', {}).get(str(seq), 0)
            event = {'arrival_time': arrival, 'message': message.to_dict()}
            events.append(event)
            if seq in f.get('duplicate', []):
                events.append(copy.deepcopy(event))
    events.sort(key=lambda e: (e['arrival_time'], e['message']['sensor_id'], e['message']['sequence_number']))
    end = max((c['samples'] - 1) * c['period'] + c['delay_limit'], max((e['arrival_time'] for e in events), default=0))
    return {'version': 1, 'config': c, 'end_time': end, 'events': events}


def validate_recording(r):
    if type(r) is not dict or set(r) != {'version', 'config', 'end_time', 'events'} or type(r['version']) is not int or r['version'] != 1:
        raise ValueError('invalid recording envelope')
    c = validate_config(r['config'])
    if not number(r['end_time']) or r['end_time'] < (c['samples'] - 1) * c['period'] + c['delay_limit']:
        raise ValueError('recording ends before final delivery deadline')
    if type(r['events']) is not list:
        raise ValueError('events must be a list')
    previous = 0
    for event in r['events']:
        if type(event) is not dict or set(event) != {'arrival_time', 'message'}:
            raise ValueError('invalid event envelope')
        t = event['arrival_time']
        if not number(t) or not previous <= t <= r['end_time']:
            raise ValueError('arrival times must be nondecreasing and within recording')
        previous = t
    return copy.deepcopy(r)


def save_recording(recording, path):
    Path(path).write_text(json.dumps(validate_recording(recording), indent=2, allow_nan=False) + '\n', encoding='utf-8')


def load_recording(path):
    return validate_recording(json.loads(Path(path).read_text(encoding='utf-8')))


class Sensor:
    def __init__(self):
        self.state = Health.RECOVERING
        self.seen = set()
        self.highest = -1
        self.latest_sequence = -1
        self.latest = None
        self.last_good = None
        self.clean = 0
        self.errors = dict.fromkeys(ERRORS, 0)
        self.latencies = []
        self.arrivals = []
        self.missing = set()
        self.ever_missing = set()
        self.history = []


class Engine:
    def __init__(self, recording):
        self.recording = validate_recording(recording)
        self.config = self.recording['config']
        self.reset()

    def reset(self):
        self.now = 0.
        self.cursor = 0
        self.sensors = {sid: Sensor() for sid in IDS}
        self.rejected_unknown = 0

    def _clock(self, t):
        c = self.config
        for s in self.sensors.values():
            due = min(c['samples'], max(0, math.floor((t - c['delay_limit']) / c['period'] + 1e-10) + 1))
            missing = set(range(max(due, s.highest + 1))) - s.seen
            if missing - s.ever_missing:
                s.clean = 0
                s.state = Health.DEGRADED
            s.missing = missing
            s.ever_missing |= missing
            if t - (s.last_good if s.last_good is not None else 0) >= c['offline_after']:
                s.state = Health.OFFLINE
                s.clean = 0
        self.now = t

    def _receive(self, event):
        raw = event['message']
        sensor = raw.get('sensor_id') if isinstance(raw, dict) else None
        if type(sensor) is not str or sensor not in self.sensors:
            self.rejected_unknown += 1
            return
        s = self.sensors[sensor]
        try:
            m = Message.parse(raw)
            if m.sequence_number >= self.config['samples'] or m.timestamp > self.now or not math.isclose(m.timestamp, m.sequence_number * self.config['period'], abs_tol=1e-9, rel_tol=0):
                raise ValueError('message violates scheduled stream contract')
        except ValueError:
            s.errors['invalid'] += 1
            s.clean = 0
            if s.state != Health.OFFLINE:
                s.state = Health.DEGRADED
            return
        flags = []
        seq = m.sequence_number
        latency = self.now - m.timestamp
        duplicate = seq in s.seen
        if duplicate:
            flags.append('duplicate')
        else:
            if seq < s.highest:
                flags.append('out_of_order')
            s.seen.add(seq)
            s.highest = max(seq, s.highest)
            s.arrivals.append(self.now)
            s.latencies.append(latency)
        if latency >= self.config['delay_limit']:
            flags.append('delayed')
        if m.quality_flag == 'BAD' or not -100 <= m.measurement_value <= 100:
            flags.append('invalid')
        for flag in flags:
            s.errors[flag] += 1
        if not duplicate and 'invalid' not in flags:
            s.last_good = self.now
            if seq > s.latest_sequence:
                s.latest, s.latest_sequence = m.measurement_value, seq
            s.history.append((m.timestamp, m.measurement_value))
        if flags:
            s.clean = 0
            if s.state != Health.OFFLINE or s.last_good == self.now:
                s.state = Health.DEGRADED
        else:
            s.clean += 1
            s.state = Health.HEALTHY if s.clean >= self.config['recovery_messages'] else Health.RECOVERING
        self._clock(self.now)

    def advance(self, t):
        if not number(t) or not self.now <= t <= self.recording['end_time']:
            raise ValueError('advance requires monotonic time within recording')
        events = self.recording['events']
        while self.cursor < len(events) and events[self.cursor]['arrival_time'] <= t:
            e = events[self.cursor]
            self._clock(e['arrival_time'])
            self._receive(e)
            self.cursor += 1
        self._clock(t)
        return self.snapshot()

    def seek(self, t):
        if not number(t) or not 0 <= t <= self.recording['end_time']:
            raise ValueError('seek outside recording')
        self.reset()
        return self.advance(t)

    def snapshot(self):
        rows = []
        for sid, s in self.sensors.items():
            denominator = len(s.seen) + len(s.missing)
            rows.append(dict(sensor_id=sid, state=s.state.value, latest_measurement=s.latest,
                message_rate_hz=sum(self.now - 1 < t <= self.now for t in s.arrivals),
                received_unique=len(s.seen), missing_messages=len(s.missing),
                missing_detected_total=len(s.ever_missing),
                packet_loss=len(s.missing) / denominator if denominator else 0.,
                latency_mean_seconds=float(np.mean(s.latencies)) if s.latencies else None,
                latency_latest_seconds=s.latencies[-1] if s.latencies else None,
                **{f'{k}_errors': v for k, v in s.errors.items()},
                error_count=sum(s.errors.values()) + len(s.ever_missing)))
        return {'time': self.now, 'rejected_unknown': self.rejected_unknown, 'sensors': rows}

    def export(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        report = self.snapshot()
        (directory / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        with (directory / 'report.csv').open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(report['sensors'][0]))
            writer.writeheader()
            writer.writerows(report['sensors'])
        with (directory / 'messages.csv').open('w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['arrival_time', 'message_json'])
            for e in self.recording['events'][:self.cursor]:
                writer.writerow([e['arrival_time'], json.dumps(e['message'], sort_keys=True, allow_nan=False)])
