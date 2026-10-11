"""Single-window Matplotlib presentation with shared-clock widget callbacks."""
import os
import sys
import time
from pathlib import Path
import numpy as np
from demo.mock_estimator import MockEstimator
from .controller import Controller
from .scenarios import DISCLAIMER, MAP_DISCLAIMER

COLORS = {'HEALTHY':'#67e8b0', 'DEGRADED':'#ffce73', 'OFFLINE':'#ff8294', 'RECOVERING':'#81b9ff', 'TRACKING':'#67e8b0', 'LOST':'#ff8294', 'REACQUIRING':'#81b9ff'}
BG, PANEL, TEXT, MUTED = '#0a1220', '#142239', '#f0f5fc', '#adc0d8'


class IntegratedDashboard:
    def __init__(self, controller, presentation=False):
        import matplotlib.pyplot as plt
        from matplotlib.patches import Circle
        from matplotlib.colors import LinearSegmentedColormap
        self.plt, self.controller = plt, controller
        self.presentation = presentation
        self.exporting = False
        self.last_tick = time.perf_counter()
        self.timer = None
        self.widgets = []
        self._updating = False
        self._map_key = None
        self.mock = MockEstimator(controller.player.scenario)
        self.fig = plt.figure(figsize=(16, 9), dpi=90, facecolor=BG)
        self.fig.text(.045, .95, DISCLAIMER, color='#81b9ff', fontsize=24 if presentation else 21, weight='bold')
        self.title = self.fig.text(.045, .902, '', color=TEXT, fontsize=19, weight='bold')
        self.mode = self.fig.text(.96, .946, '', color='#67e8b0', fontsize=15, weight='bold', ha='right')
        self.fig.text(.045, .862, MAP_DISCLAIMER, color='#ffce73', fontsize=11, weight='bold')
        self.fig.text(.545, .862, 'INDEPENDENT SYNTHETIC TELEMETRY', color=MUTED, fontsize=12, weight='bold')
        self.map = self.fig.add_axes([.045, .345, .455, .475], facecolor=PANEL)
        self.map.set_aspect('equal')
        self.map.tick_params(colors=MUTED, labelsize=10)
        self.map.set_xlabel('Authored map x (m)', color=MUTED)
        self.map.set_ylabel('Authored map y (m)', color=MUTED)
        self.map.grid(color=MUTED, alpha=.13)
        for spine in self.map.spines.values():
            spine.set_color('#35506e')
        cmap = LinearSegmentedColormap.from_list('integrated_fixture', [PANEL,'#20536a','#46bdae'])
        self.blob = self.map.imshow(np.zeros((2,2)), origin='lower', cmap=cmap, interpolation='nearest', zorder=1)
        self.tail, = self.map.plot([], [], color='#c5d6ed', lw=2, zorder=3)
        self.marker, = self.map.plot([], [], 'o', color='white', markersize=8, zorder=5)
        self.ring = Circle((0,0), 1, fill=False, edgecolor='#67e8b0', linestyle='--', lw=2, zorder=4)
        self.map.add_patch(self.ring)
        self.gap = self.map.text(.5,.5,'NO PREDEFINED POSITION', transform=self.map.transAxes, ha='center', va='center', color='#ffce73', fontsize=16, weight='bold', bbox=dict(facecolor=PANEL, edgecolor='none', pad=12), zorder=6)
        self.map_status = self.fig.text(.045, .267, '', color=TEXT, fontsize=12)
        self.cards = []
        for index in range(4):
            left = .545 + .225 * (index%2)
            bottom = .565 if index < 2 else .30
            ax = self.fig.add_axes([left,bottom,.212,.255], facecolor=PANEL)
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_color('#35506e')
            name = ax.text(.06,.92,f'SENSOR {index+1}', color=MUTED, fontsize=10, weight='bold')
            health = ax.text(.06,.77,'', fontsize=17 if presentation else 15, weight='bold')
            latest = ax.text(.06,.61,'', color=TEXT, fontsize=13)
            detail = ax.text(.06,.49,'', color=MUTED, fontsize=10.5, va='top', linespacing=1.35, family='DejaVu Sans Mono')
            self.cards.append((name,health,latest,detail))
        self.aggregate = self.fig.text(.045,.213,'',color=TEXT,fontsize=12)
        self.fig.text(.045,.18,'Presentation pairing only: telemetry faults do not cause the authored map behavior.', color='#ffce73', fontsize=11)
        self._create_controls()
        self.render()
        self.fig.canvas.mpl_connect('close_event', lambda event: self.timer.stop() if self.timer else None)

    def _create_controls(self):
        from matplotlib.widgets import Button, Slider
        controls = [('PLAY', .045, .065, self.play), ('PAUSE', .115,.065,self.pause), ('RESET', .185,.065,self.reset)]
        controls += [(f'{v:g}x', .28+i*.05,.045,lambda event,v=v:self.set_speed(v)) for i,v in enumerate((.5,1.,2.))]
        controls += [(name.upper(), .545+i*.14,.13,lambda event,name=name:self.switch(name)) for i,name in enumerate(('normal','uncertain','lost'))]
        for label, left, width, callback in controls:
            button = Button(self.fig.add_axes([left,.112,width,.044]),label,color='#d4e4f5',hovercolor='#81b9ff')
            button.on_clicked(callback)
            self.widgets.append(button)
        self.slider = Slider(self.fig.add_axes([.105,.065,.79,.02],facecolor=PANEL), 'TIME', 0, self.controller.clock.duration, valinit=0, valfmt='%.2f s', color='#67e8b0')
        self.slider.label.set_color(TEXT)
        self.slider.valtext.set_color(TEXT)
        self.slider.on_changed(self.seek)
        self.fig.text(.045,.021,'Dashed ring: authored visual radius  |  Trace: past authored frames  |  Measurements: arbitrary scalar units', color=MUTED, fontsize=10)

    def render(self):
        c = self.controller
        s = c.snapshot()
        f = c.player.current_frame
        key = (id(c.player.scenario), c.player.frame_index)
        if key != self._map_key:
            if self.mock.scenario is not c.player.scenario:
                self.mock = MockEstimator(c.player.scenario)
            result = self.mock.estimate(c.player.frame_index)  # Only an authored frame index.
            available = f.position is not None
            for artist in (self.blob,self.marker,self.ring):
                artist.set_visible(available)
            self.gap.set_visible(not available)
            scenario = c.player.scenario
            self.map.set_xlim(0,scenario.area_width_m)
            self.map.set_ylim(0,scenario.area_height_m)
            self.blob.set_extent((0,scenario.area_width_m,0,scenario.area_height_m))
            if available:
                self.blob.set_data(result.probability_grid)
                self.blob.set_clim(0,float(result.probability_grid.max()))
                self.marker.set_data([f.position[0]],[f.position[1]])
                self.ring.center, self.ring.radius = f.position, f.uncertainty_radius
            else:
                self.marker.set_data([],[])
                self.gap.set_text('NO PREDEFINED POSITION\n'+f.track_status)
            self.tail.set_data([x.position[0] if x.position else np.nan for x in c.player.history], [x.position[1] if x.position else np.nan for x in c.player.history])
            self._map_key = key
        self.title.set_text(f'{c.name.upper()}  /  {c.clock.time:05.2f} — {c.clock.duration:g} s')
        mode = 'EXPORT' if self.exporting else 'PLAYING' if c.clock.playing else 'FINISHED' if c.clock.time == c.clock.duration else 'PAUSED'
        self.mode.set_text(f'{mode}   {c.clock.speed:g}x')
        hold = ' | final map frame held' if s['map_held_at_end'] else ''
        self.map_status.set_text(f'Authored status: {f.track_status}  |  Frame time: {f.time:g}s{hold}')
        self.map_status.set_color(COLORS.get(f.track_status,TEXT))
        for row, (_,health,latest,detail) in zip(s['telemetry']['sensors'],self.cards):
            health.set_text(row['state'])
            health.set_color(COLORS[row['state']])
            value = row['latest_measurement']
            latest.set_text('Latest usable: —' if value is None else f'Latest usable: {value:.3f}')
            stamp = '—' if row['last_message_timestamp'] is None else f"{row['last_message_timestamp']:.2f}s"
            seq = '—' if row['last_sequence_number'] is None else str(row['last_sequence_number'])
            latency = '—' if row['latency_latest_seconds'] is None else f"{row['latency_latest_seconds']:.2f}s"
            detail.set_text(f"Last msg {stamp} / seq {seq}\nRate {row['message_rate_hz']:g}/s   Loss {row['packet_loss']:.1%}\nMissing {row['missing_messages']}   Dup {row['duplicate_errors']}\nDelayed {row['delayed_errors']}   Invalid {row['invalid_errors']}\nReorder {row['out_of_order_errors']}   Lat {latency}")
        rows = s['telemetry']['sensors']
        self.aggregate.set_text(f"TOTAL   {sum(r['received_unique'] for r in rows)} received   |   {sum(r['missing_messages'] for r in rows)} missing   |   {sum(r['error_count'] for r in rows)} error flags   |   {sum(r['message_rate_hz'] for r in rows):g} msg/s   |   {s['telemetry']['rejected_unknown']} unknown-ID rejects")
        self._updating = True
        try:
            self.slider.valmax = c.clock.duration
            self.slider.ax.set_xlim(0,c.clock.duration)
            self.slider.set_val(c.clock.time)
        finally:
            self._updating = False

    def _refresh(self):
        self.last_tick = time.perf_counter()
        self.render()
        self.fig.canvas.draw_idle()

    def play(self, _event=None):
        self.controller.play()
        self._refresh()

    def pause(self, _event=None):
        self.controller.pause()
        self._refresh()

    def reset(self, _event=None):
        self.controller.reset()
        self._refresh()

    def set_speed(self, speed):
        self.controller.set_speed(speed)
        self._refresh()

    def seek(self, value):
        if not self._updating:
            self.controller.seek(float(value))
            self._refresh()

    def switch(self, name):
        self.controller.switch(name)
        self._map_key = None
        self._refresh()

    def tick(self):
        now = time.perf_counter()
        self.controller.advance(max(0., now-self.last_tick))
        self.last_tick = now
        self.render()
        self.fig.canvas.draw_idle()

    def show(self):
        self.timer = self.fig.canvas.new_timer(interval=100)
        self.timer.add_callback(self.tick)
        self.last_tick = time.perf_counter()
        self.timer.start()
        self.plt.show()


def run_integrated(name, speed, presentation, headless, save, output_root, seed=42, replay=None):
    try:
        import matplotlib
    except ImportError as exc:
        raise ValueError('Integrated visualization requires Matplotlib; install requirements.txt') from exc
    from .reporting import load_manifest, export_animation
    c = load_manifest(replay) if replay else Controller(name,seed,speed)
    if headless or (os.name != 'nt' and sys.platform != 'darwin' and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))):
        matplotlib.use('Agg')
        headless = True
    try:
        dashboard = IntegratedDashboard(c,presentation)
    except ImportError as exc:
        raise ValueError('Visualization backend unavailable; use --headless or install a GUI backend') from exc
    if matplotlib.get_backend().lower() in ('agg','pdf','svg','ps','cairo','template'):
        headless = True
    output = Path(output_root)/'integrated'/c.name
    try:
        if save or headless:
            export_animation(dashboard,output,save or 'both')
        if not headless:
            dashboard.show()
    finally:
        dashboard.plt.close(dashboard.fig)
    return output
