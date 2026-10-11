"""Self-contained deterministic replay manifests and presentation exports."""
import json
from pathlib import Path
import tempfile
from .controller import Controller
from .scenarios import DISCLAIMER, MAP_DISCLAIMER


def manifest(controller):
    return dict(version=1, data_source=DISCLAIMER, map_source=MAP_DISCLAIMER,
                scenario=controller.name, demo=controller.demo_data,
                telemetry_recording=controller.telemetry.recording,
                playback_time=controller.clock.time, speed=controller.clock.speed,
                playing=controller.clock.playing)


def load_manifest(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        fields = {'version','data_source','map_source','scenario','demo','telemetry_recording','playback_time','speed','playing'}
        if type(data) is not dict or set(data) != fields or type(data['version']) is not int or data['version'] != 1 or data['data_source'] != DISCLAIMER or data['map_source'] != MAP_DISCLAIMER or type(data['playing']) is not bool:
            raise ValueError('Invalid integrated replay manifest schema')
        c = Controller.from_payload(data['scenario'], data['demo'], data['telemetry_recording'], data['speed'])
        c.seek(data['playback_time'])
        if data['playing']:
            c.play()
        return c
    except (ValueError, OSError, UnicodeError, TypeError) as exc:
        raise ValueError(f'Cannot load integrated replay manifest: {exc}') from exc


def export_reports(controller, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    controller.telemetry.export(output)
    (output/'telemetry_summary.csv').write_bytes((output/'report.csv').read_bytes())
    (output/'replay_manifest.json').write_text(json.dumps(manifest(controller), indent=2, allow_nan=False)+'\n', encoding='utf-8')
    (output/'integrated_state.json').write_text(json.dumps(controller.snapshot(), indent=2, allow_nan=False)+'\n', encoding='utf-8')


def export_animation(dashboard, output, kind='both'):
    if kind not in ('frames', 'gif', 'both'):
        raise ValueError('Export kind must be frames, gif or both')
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError('PNG/GIF export requires Pillow; install requirements.txt') from exc
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    c = dashboard.controller
    old_time, old_playing = c.clock.time, c.clock.playing
    # 2 fps logical sampling plus exact terminal time. No interpolated map positions.
    duration = c.clock.duration
    times = [i*.5 for i in range(int(duration/.5)+1)]
    if times[-1] != duration:
        times.append(duration)
    images, durations = [], []
    c.pause()
    dashboard.exporting = True
    try:
        c.seek(0)
        for index, t in enumerate(times):
            c.clock.seek(t)
            c._sync()
            dashboard.render()
            dashboard.fig.canvas.draw()
            if kind in ('frames', 'both'):
                dashboard.fig.savefig(output/f'frame_{index:03d}.png', dpi=90, facecolor=dashboard.fig.get_facecolor())
            if kind in ('gif', 'both'):
                image = Image.frombytes('RGBA', dashboard.fig.canvas.get_width_height(), bytes(dashboard.fig.canvas.buffer_rgba()))
                images.append(image.convert('P', palette=Image.Palette.ADAPTIVE, colors=128))
                image.close()
                next_time = times[index+1] if index+1 < len(times) else t+.5
                durations.append(max(10, round((next_time-t)/c.clock.speed*100)*10))
        export_reports(c, output)
        if images:
            with tempfile.NamedTemporaryFile(dir=output, suffix='.gif', delete=False) as tmp:
                temporary = Path(tmp.name)
            try:
                images[0].save(temporary, save_all=True, append_images=images[1:], duration=durations, loop=0, disposal=2, optimize=False)
                with Image.open(temporary) as check:
                    if check.n_frames != len(images):
                        raise OSError('GIF frame count mismatch')
                    for i in range(check.n_frames):
                        check.seek(i)
                        check.load()
                temporary.replace(output/'animation.gif')
            finally:
                temporary.unlink(missing_ok=True)
        (output/'export_info.json').write_text(json.dumps(dict(frame_times=times, gif_final_hold_logical_seconds=.5, speed=c.clock.speed), indent=2)+'\n', encoding='utf-8')
    finally:
        for image in images:
            image.close()
        c.seek(old_time)
        c.clock.playing = old_playing
        dashboard.exporting = False
        dashboard.render()
