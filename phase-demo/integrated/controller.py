"""Synchronizes playback only. Telemetry never enters the authored map path."""
import copy
from dataclasses import asdict
from demo.player import DemoPlayer
from telemetry.engine import Engine
from telemetry.schema import Message
from .timeline import Timeline
from .scenarios import load_pair, normalize_recording, parse_demo, PAIRINGS


class Controller:
    def __init__(self, name='normal', seed=42, speed=1., demo_path=None, telemetry_path=None):
        scenario, data, recording = load_pair(name, seed, demo_path, telemetry_path)
        self._install(name, scenario, data, recording, speed)

    def _install(self, name, scenario, data, recording, speed):
        if type(name) is not str or name not in PAIRINGS:
            raise ValueError('Unknown integrated pairing')
        self.name = name
        self.demo_data = copy.deepcopy(data)
        self.player = DemoPlayer(scenario)
        self.telemetry = Engine(normalize_recording(scenario, recording))
        self.clock = Timeline(self.telemetry.recording['end_time'], speed)
        self._sync(reconstruct=True)

    @classmethod
    def from_payload(cls, name, demo_data, recording, speed=1.):
        obj = cls.__new__(cls)
        obj._install(name, parse_demo(demo_data), demo_data, recording, speed)
        return obj

    def switch(self, name):
        # Build first so a load error leaves the active scenario intact.
        replacement = Controller(name, self.telemetry.config['seed'], self.clock.speed)
        self.__dict__.update(replacement.__dict__)

    def _sync(self, reconstruct=False):
        t = self.clock.time
        # Holding a final authored frame never extrapolates its position.
        self.player.seek(min(t, self.player.scenario.duration_seconds))
        if reconstruct:
            self.telemetry.seek(t)
        else:
            self.telemetry.advance(t)

    def play(self):
        self.clock.play()

    def pause(self):
        self.clock.pause()

    def reset(self):
        self.clock.reset()
        self._sync(reconstruct=True)

    def set_speed(self, speed):
        self.clock.set_speed(speed)

    def advance(self, seconds):
        self.clock.advance(seconds)
        self._sync()
        return self.snapshot()

    def seek(self, t):
        self.clock.seek(t)
        self._sync(reconstruct=True)
        return self.snapshot()

    def snapshot(self):
        telemetry = self.telemetry.snapshot()
        last = {}
        # Metadata from actual consumed envelopes; no fabricated latest-message fields.
        for event in self.telemetry.recording['events'][:self.telemetry.cursor]:
            try:
                m = Message.parse(event['message'])
            except ValueError:
                continue
            sensor = self.telemetry.sensors.get(m.sensor_id)
            if sensor and m.sequence_number in sensor.seen and abs(m.timestamp - m.sequence_number * self.telemetry.config['period']) <= 1e-9 and m.timestamp <= event['arrival_time']:
                last[m.sensor_id] = (m.timestamp, m.sequence_number, event['arrival_time'])
        for row in telemetry['sensors']:
            stamp, seq, arrival = last.get(row['sensor_id'], (None, None, None))
            row.update(last_message_timestamp=stamp, last_sequence_number=seq, last_arrival_time=arrival)
        frame = asdict(self.player.current_frame)
        if frame['position'] is not None:
            frame['position'] = list(frame['position'])
        return dict(scenario=self.name, logical_time=self.clock.time, duration=self.clock.duration,
                    map_frame=frame, map_frame_index=self.player.frame_index,
                    map_held_at_end=self.clock.time > self.player.scenario.duration_seconds,
                    telemetry=telemetry)
