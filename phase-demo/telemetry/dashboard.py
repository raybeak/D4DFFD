"""Matplotlib live wall-clock playback of synthetic virtual-clock events."""
import time
import math
from pathlib import Path
from .engine import Engine


class Dashboard:
    def __init__(self, recording):
        import matplotlib.pyplot as plt
        self.engine = Engine(recording)
        self.figure, axes = plt.subplots(2, 1, figsize=(13, 8), gridspec_kw={'height_ratios': [1, 1.4]})
        self.status, self.plot = axes
        self.figure.subplots_adjust(left=.08, right=.97, top=.91, bottom=.09, hspace=.32)
        self.figure.suptitle('SYNTHETIC SCALAR TELEMETRY | Four independent streams', fontsize=15)
        self.status.axis('off')
        self.lines = {sid: self.plot.plot([], [], label=sid)[0] for sid in self.engine.sensors}
        self.plot.set(xlabel='Synthetic timestamp (seconds)', ylabel='Arbitrary scalar value', ylim=(-5, 40), xlim=(0, max(1, recording['end_time'])))
        self.plot.grid(alpha=.2)
        self.plot.legend(loc='upper left', ncol=4)
        self.table = None
        self.animation = None
        self.update(0)

    def update(self, t):
        report = self.engine.advance(t)
        if self.table is not None:
            self.table.remove()
        rows = []
        colors = []
        palette = {'HEALTHY': '#d9f2df', 'DEGRADED': '#fff0b3', 'OFFLINE': '#ffd9d9', 'RECOVERING': '#dceaff'}
        for r in report['sensors']:
            latest = r['latest_measurement']
            latency = r['latency_latest_seconds']
            rows.append([r['sensor_id'], r['state'], '—' if latest is None else f'{latest:.3f}', str(r['message_rate_hz']), f"{100*r['packet_loss']:.1f}%", '—' if latency is None else f'{latency:.3f}s', str(r['missing_messages']), str(r['error_count'])])
            colors.append([palette[r['state']]] * 8)
        self.table = self.status.table(cellText=rows, colLabels=['Sensor', 'Health', 'Latest', 'Rate /s', 'Loss', 'Latency', 'Missing', 'Errors'], cellColours=colors, cellLoc='center', loc='center')
        self.table.auto_set_font_size(False)
        self.table.set_fontsize(10)
        self.table.scale(1, 2)
        self.status.set_title(f'Virtual time {t:.2f}s | rate: trailing 1s | loss: unresolved / expected | latency: latest unique packet', fontsize=10)
        for sid, line in self.lines.items():
            history = sorted(self.engine.sensors[sid].history)[-300:]
            xs, ys = [], []
            previous = None
            for stamp, value in history:
                if previous is not None and stamp - previous > self.engine.config['period'] * 1.01:
                    xs.append(float('nan'))
                    ys.append(float('nan'))
                xs.append(stamp)
                ys.append(value)
                previous = stamp
            line.set_data(xs, ys)
        self.plot.relim()
        self.plot.autoscale_view(scalex=False, scaley=True)
        self.plot.set_autoscaley_on(True)
        return report

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.figure.savefig(path, dpi=130)

    def run(self, speed=1.):
        if not math.isfinite(speed) or speed <= 0:
            raise ValueError('speed must be positive and finite')
        import matplotlib.pyplot as plt
        from matplotlib.animation import FuncAnimation
        start = time.monotonic()
        def frame(_):
            t = min(self.engine.recording['end_time'], (time.monotonic() - start) * speed)
            self.update(t)
            if t >= self.engine.recording['end_time'] and self.animation:
                self.animation.event_source.stop()
        self.animation = FuncAnimation(self.figure, frame, interval=100, cache_frame_data=False)
        plt.show()
