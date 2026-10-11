"""Explicit presentation pairings. No causal link between the paired streams."""
import copy
import json
from pathlib import Path
import tempfile
from demo.scenario import load_scenario
from telemetry.engine import generate, validate_recording

ROOT = Path(__file__).resolve().parent.parent
PAIRINGS = {'normal': 'normal', 'uncertain': 'mixed_faults', 'lost': 'outage_recovery'}
DISCLAIMER = 'SYNTHETIC DEMONSTRATION'
MAP_DISCLAIMER = 'PREDEFINED POSITIONS — NOT SENSOR-DERIVED'


def parse_demo(data):
    # Reuse the original strict file loader without changing its API.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'scenario.json'
        path.write_text(json.dumps(data, allow_nan=False), encoding='utf-8')
        return load_scenario(path)


def load_pair(name, seed=42, demo_path=None, telemetry_path=None):
    if type(name) is not str or name not in PAIRINGS:
        raise ValueError('Invalid pairing; choose normal, uncertain or lost')
    demo_path = Path(demo_path) if demo_path else ROOT/'demo'/'scenarios'/f'{name}.json'
    telemetry_path = Path(telemetry_path) if telemetry_path else ROOT/'telemetry'/'scenarios'/f'{PAIRINGS[name]}.json'
    try:
        data = json.loads(demo_path.read_text(encoding='utf-8'))
        scenario = load_scenario(demo_path)
        config = json.loads(telemetry_path.read_text(encoding='utf-8'))
        if type(config) is not dict:
            raise ValueError('Telemetry configuration must be an object')
        config['seed'] = seed
        recording = generate(config)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f'Cannot load integrated pairing {name}: {exc}') from exc
    return scenario, data, recording


def normalize_recording(scenario, recording):
    recording = validate_recording(recording)
    # Extend only the monitor horizon; source messages and their timestamps stay intact.
    recording['end_time'] = max(scenario.duration_seconds, recording['end_time'])
    return copy.deepcopy(recording)
