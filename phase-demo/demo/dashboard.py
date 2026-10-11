"""Matplotlib UI for scripted frames. Imports plotting only after backend selection."""
from pathlib import Path
from time import perf_counter
import json
import os
import sys
import tempfile
import numpy as np
from demo.mock_estimator import MockEstimator
from demo.player import DemoPlayer
from demo.scenario import builtin_scenario
from config import ExperimentConfig

STATE_COLORS = {"TRACKING": "#56e0b8", "DEGRADED": "#ffce6b", "LOST": "#ff6e82", "REACQUIRING": "#77b7ff"}


class DemoDashboard:
    def __init__(self, player: DemoPlayer, presentation: bool = False):
        import matplotlib.pyplot as plt
        from matplotlib.colors import LinearSegmentedColormap
        from matplotlib.patches import Circle
        self.plt = plt
        self.player = player
        self.mock = MockEstimator(player.scenario)
        self.widgets = []
        self.last_tick = perf_counter()
        self.timer = None
        self.exporting = False
        self.last_rendered = None
        self.fig = plt.figure(figsize=(14.4, 8.1), facecolor="#0a1324")
        self.ax = self.fig.add_axes([.055, .16, .57, .67], facecolor="#101f34")
        self.panel = self.fig.add_axes([.67, .18, .30, .63], facecolor="#101f34")
        self.panel.set_axis_off()
        title_size = 23 if presentation else 21
        self.fig.text(.055, .94, "SIMULATED DISTRIBUTED-SENSOR DEMO", color="#eef4ff", fontsize=title_size, weight="bold")
        self.fig.text(.055, .887, "SIMULATED / PREDEFINED DATA    •    NO POSITION INFERENCE", color="#ffce6b", fontsize=13, weight="bold")
        s = player.scenario
        self.ax.set(xlim=(0, s.area_width_m), ylim=(0, s.area_height_m), xlabel="x / East (m)", ylabel="y / North (m)")
        self.ax.set_aspect("equal")
        self.ax.tick_params(colors="#aebed3", labelsize=11)
        self.ax.xaxis.label.set_color("#aebed3")
        self.ax.yaxis.label.set_color("#aebed3")
        for spine in self.ax.spines.values():
            spine.set_color("#3a526e")
        self.ax.grid(color="#3a526e", alpha=.3)
        cmap = LinearSegmentedColormap.from_list("demo_blob", ["#101f34", "#173e52", "#247880", "#5de8cb"])
        self.blob = self.ax.imshow(np.zeros((2, 2)), origin="lower", extent=(0, s.area_width_m, 0, s.area_height_m),
                                   cmap=cmap, vmin=0, vmax=1, interpolation="nearest", zorder=1)
        receivers = ExperimentConfig().receivers
        self.ax.scatter([r.x for r in receivers], [r.y for r in receivers], marker="^", s=85, c="#e0e8f7", zorder=4)
        for r in receivers:
            self.ax.annotate(r.receiver_id.upper(), (r.x, r.y), xytext=(7, 7), textcoords="offset points", color="#c3d4ec", fontsize=10)
        self.tail, = self.ax.plot([], [], color="#a8c1de", linewidth=2, alpha=.8, zorder=5)
        self.marker, = self.ax.plot([], [], marker="o", color="#f9fbff", markeredgecolor="#0a1324", markeredgewidth=2,
                                    markersize=10, linestyle="none", zorder=7)
        self.ring = Circle((0, 0), 1, fill=False, edgecolor="#5de8cb", linewidth=2, linestyle="--", zorder=6)
        self.ax.add_patch(self.ring)
        self.gap = self.ax.text(.5, .52, "", ha="center", va="center", transform=self.ax.transAxes,
                                color="#ffce6b", fontsize=19, weight="bold", zorder=9,
                                bbox=dict(facecolor="#101f34", edgecolor="none", alpha=.9, pad=12))
        self.panel.text(0, 1, "DEMO MODE", color="#77b7ff", fontsize=14, weight="bold")
        self.panel.text(0, .92, s.scenario_name, color="#eef4ff", fontsize=20, weight="bold")
        self.state_text = self.panel.text(0, .78, "", fontsize=27, weight="bold")
        self.position_text = self.panel.text(0, .64, "", color="#eef4ff", fontsize=19)
        self.detail_text = self.panel.text(0, .49, "", color="#c3d4ec", fontsize=15, va="top", linespacing=1.65)
        self.panel.text(0, .055, "Position, radius and confidence\nare scripted. No measured accuracy.", color="#ffce6b", fontsize=11, linespacing=1.6)
        self.fig.text(.055, .055, "Dashed ring = predefined visual radius   |   Tail = past authored positions only", color="#aebed3", fontsize=11)
        self.fig.text(.055, .025, "Space: play / pause     R: reset     1 / 2 / 3: 0.5x / 1x / 2x", color="#7790ae", fontsize=10)
        self.render()

    def render(self) -> None:
        p = self.player
        frame = p.current_frame
        color = STATE_COLORS[frame.track_status]
        if self.last_rendered != p.frame_index:
            result = self.mock.estimate(p.frame_index)
            available = result.representative_position is not None
            self.blob.set_visible(available)
            self.marker.set_visible(available)
            self.ring.set_visible(available)
            self.gap.set_visible(not available)
            if available:
                self.blob.set_data(result.probability_grid)
                self.blob.set_clim(0, float(result.probability_grid.max()))
                self.marker.set_data([frame.position[0]], [frame.position[1]])
                self.ring.center = frame.position
                self.ring.radius = frame.uncertainty_radius
                self.ring.set_edgecolor(color)
            else:
                self.gap.set_text("NO PREDEFINED POSITION\n"+frame.track_status)
            # NaN breaks the line across missing frames; do not bridge lost intervals.
            self.tail.set_data([f.position[0] if f.position else np.nan for f in p.history],
                               [f.position[1] if f.position else np.nan for f in p.history])
            self.last_rendered = p.frame_index
        self.state_text.set_text(frame.track_status)
        self.state_text.set_color(color)
        self.position_text.set_text("Mock position: unavailable" if frame.position is None else f"Mock position: ({frame.position[0]:.1f}, {frame.position[1]:.1f}) m")
        radius = "N/A" if frame.uncertainty_radius is None else f"{frame.uncertainty_radius:.1f} m"
        mode = "REPLAY EXPORT" if self.exporting else "PLAYING" if p.playing else "FINISHED" if p.elapsed >= p.scenario.duration_seconds else "PAUSED"
        self.detail_text.set_text(f"Time     {p.elapsed:05.1f} / {p.scenario.duration_seconds:.0f} s\n"
                                  f"Confidence     {frame.confidence_label}\nVisual radius     {radius}\n"
                                  f"Frame     {p.frame_index+1} / {len(p.scenario.frames)}\n"
                                  f"Playback     {mode}  |  {p.speed:g}x")

    def reset(self, _event=None) -> None:
        self.player.reset()
        self.last_rendered = None
        self.last_tick = perf_counter()
        self.render()
        self.fig.canvas.draw_idle()

    def toggle(self, _event=None) -> None:
        if self.player.playing:
            self.player.pause()
        else:
            self.player.play()
        self.last_tick = perf_counter()
        self.render()
        self.fig.canvas.draw_idle()

    def set_speed(self, speed: float) -> None:
        self.player.set_speed(speed)
        self.last_tick = perf_counter()
        self.render()
        self.fig.canvas.draw_idle()

    def keypress(self, event) -> None:
        if event.key == " ":
            self.toggle()
        elif event.key in ("r", "R"):
            self.reset()
        elif event.key in ("1", "2", "3"):
            self.set_speed({"1": .5, "2": 1., "3": 2.}[event.key])

    def tick(self) -> None:
        now = perf_counter()
        self.player.advance(max(0, now-self.last_tick))
        self.last_tick = now
        self.render()
        self.fig.canvas.draw_idle()

    def show(self) -> None:
        from matplotlib.widgets import Button
        for label, left, callback in (("PLAY / PAUSE", .67, self.toggle), ("RESET", .855, self.reset)):
            button = Button(self.fig.add_axes([left, .09, .16 if left == .67 else .105, .055]), label,
                            color="#d3e5f2", hovercolor="#56e0b8")
            button.on_clicked(callback)
            self.widgets.append(button)
        self.fig.canvas.mpl_connect("key_press_event", self.keypress)
        self.timer = self.fig.canvas.new_timer(interval=80)
        self.timer.add_callback(self.tick)
        self.fig.canvas.mpl_connect("close_event", lambda _event: self.timer.stop())
        self.player.play()
        self.last_tick = perf_counter()
        self.timer.start()
        self.plt.show()


def export_demo(dashboard: DemoDashboard, output: Path, kind: str) -> None:
    """Export authored frames only. GIF uses timestamp gaps, not synthesized frames."""
    from PIL import Image
    output.mkdir(parents=True, exist_ok=True)
    player = dashboard.player
    original_time, original_playing = player.elapsed, player.playing
    images, durations, records = [], [], []
    player.pause()
    dashboard.exporting = True
    try:
        for index, frame in enumerate(player.scenario.frames):
            player.seek(frame.time)
            dashboard.render()
            dashboard.fig.canvas.draw()
            if kind in ("frames", "both"):
                dashboard.fig.savefig(output/f"frame_{index:03d}.png", dpi=100, facecolor=dashboard.fig.get_facecolor())
            if kind in ("gif", "both"):
                rgb = np.asarray(dashboard.fig.canvas.buffer_rgba())[:, :, :3]
                images.append(Image.fromarray(rgb.copy()).convert("P", palette=Image.Palette.ADAPTIVE, colors=128))
                # Final authored frame holds for one additional demo second.
                next_time = player.scenario.frames[index+1].time if index+1 < len(player.scenario.frames) else frame.time+1
                durations.append(max(10, round((next_time-frame.time)/player.speed*1000/10)*10))
            records.append(dict(frame_index=index, time_seconds=frame.time, position=frame.position,
                                uncertainty_radius_m=frame.uncertainty_radius, track_status=frame.track_status,
                                confidence_label=frame.confidence_label))
        if images:
            # Verify a completed temporary GIF before replacing any previous export.
            with tempfile.NamedTemporaryFile(dir=output, suffix=".gif", delete=False) as stream:
                temporary_gif = Path(stream.name)
            try:
                images[0].save(temporary_gif, save_all=True, append_images=images[1:],
                               duration=durations, loop=0, disposal=2, optimize=False)
                with Image.open(temporary_gif) as check:
                    if check.n_frames != len(images):
                        raise OSError("Exported GIF does not contain every predefined frame")
                    for index in range(check.n_frames):
                        check.seek(index)
                        check.load()
                temporary_gif.replace(output/"animation.gif")
            finally:
                temporary_gif.unlink(missing_ok=True)
        (output/"replay_manifest.json").write_text(json.dumps(dict(
            data_source="SIMULATED / PREDEFINED DATA", scenario=player.scenario.scenario_name,
            area_width_m=player.scenario.area_width_m, area_height_m=player.scenario.area_height_m,
            grid_resolution_m=player.scenario.grid_resolution_m,
            speed=player.speed, algorithm="NONE - scripted replay",
            radius_meaning="predefined visual radius, not calibrated confidence",
            gif_final_hold_demo_seconds=1, frames=records), indent=2)+"\n", encoding="utf-8")
    finally:
        for image in images:
            image.close()
        player.seek(original_time)
        player.playing = original_playing
        dashboard.exporting = False
        dashboard.last_rendered = None
        dashboard.render()


def run_demo(name: str, speed: float, presentation: bool, headless: bool,
             save: str | None, output_root: Path) -> Path:
    import matplotlib
    if headless or (os.name != "nt" and sys.platform != "darwin"
                    and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))):
        matplotlib.use("Agg")
        headless = True
    # Do not import the Phase 1 plotting modules: they select a headless backend.
    dashboard = DemoDashboard(DemoPlayer(builtin_scenario(name), speed), presentation)
    if matplotlib.get_backend().lower() in ("agg", "pdf", "svg", "ps", "cairo", "template"):
        headless = True
    output = output_root/"demo"/name
    try:
        if save or headless:
            export_demo(dashboard, output, save or "gif")
        if not headless:
            dashboard.show()
    finally:
        dashboard.plt.close(dashboard.fig)
    return output
