"""Strict, versioned JSON format for manually authored visual demo frames."""
from dataclasses import dataclass
import json
import math
from pathlib import Path

STATES = {"TRACKING", "DEGRADED", "LOST", "REACQUIRING"}
CONFIDENCE = {"LOW", "MEDIUM", "HIGH", "UNKNOWN"}
BUILTINS = {"normal": "normal.json", "uncertain": "uncertain.json", "lost": "lost.json"}


def finite_number(value: object, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


@dataclass(frozen=True)
class DemoFrame:
    time: float
    position: tuple[float, float] | None
    uncertainty_radius: float | None
    confidence_label: str
    track_status: str


@dataclass(frozen=True)
class DemoScenario:
    scenario_name: str
    duration_seconds: float
    area_width_m: float
    area_height_m: float
    grid_resolution_m: float
    frames: tuple[DemoFrame, ...]


def load_scenario(path: Path) -> DemoScenario:
    """Parse explicit positions/states; never fill gaps or infer transitions."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError(f"Invalid scenario JSON: {exc}") from exc
    expected = {"schema_version", "data_source", "scenario_name", "duration_seconds",
                "area_width_m", "area_height_m", "grid_resolution_m", "frames"}
    if type(data) is not dict or set(data) != expected:
        raise ValueError("Scenario fields do not match schema version 1")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1 or data["data_source"] != "SIMULATED / PREDEFINED DATA":
        raise ValueError("Unsupported schema or missing predefined-data label")
    if not isinstance(data["scenario_name"], str) or not data["scenario_name"].strip() or len(data["scenario_name"]) > 80:
        raise ValueError("Invalid scenario name")
    duration = finite_number(data["duration_seconds"], "duration_seconds")
    width = finite_number(data["area_width_m"], "area_width_m")
    height = finite_number(data["area_height_m"], "area_height_m")
    step = finite_number(data["grid_resolution_m"], "grid_resolution_m")
    if min(duration, width, height, step) <= 0:
        raise ValueError("Duration and spatial sizes must be positive")
    for length in (width, height):
        if length/step < 1 or not math.isclose(length/step, round(length/step), abs_tol=1e-9):
            raise ValueError("Area must contain integer grid-cell counts")
    if (width/step)*(height/step) > 1_000_000:
        raise ValueError("Grid too large for demo")
    raw_frames = data["frames"]
    if type(raw_frames) is not list or not raw_frames or len(raw_frames) > 10000:
        raise ValueError("Scenario needs 1 to 10000 frames")
    frames = []
    for raw in raw_frames:
        if type(raw) is not dict or set(raw) != {"time", "position", "uncertainty_radius", "confidence_label", "track_status"}:
            raise ValueError("Invalid frame fields")
        t = finite_number(raw["time"], "frame time")
        if t < 0 or t > duration or (frames and t <= frames[-1].time):
            raise ValueError("Frame times must strictly increase within scenario duration")
        if not isinstance(raw["track_status"], str) or raw["track_status"] not in STATES:
            raise ValueError("Unknown demo status")
        if not isinstance(raw["confidence_label"], str) or raw["confidence_label"] not in CONFIDENCE:
            raise ValueError("Unknown scripted confidence label")
        position, radius = raw["position"], raw["uncertainty_radius"]
        if position is None:
            if radius is not None or raw["confidence_label"] != "UNKNOWN" or raw["track_status"] not in ("DEGRADED", "LOST"):
                raise ValueError("Missing position requires missing radius, UNKNOWN confidence and DEGRADED/LOST")
        else:
            if type(position) is not list or len(position) != 2:
                raise ValueError("Position must be [x,y] or null")
            position = tuple(finite_number(v, "position") for v in position)
            radius = finite_number(radius, "uncertainty_radius")
            if not 0 <= position[0] <= width or not 0 <= position[1] <= height or radius <= 0:
                raise ValueError("Position outside area or nonpositive radius")
            if raw["track_status"] == "LOST" or raw["confidence_label"] == "UNKNOWN":
                raise ValueError("LOST cannot have a position; available positions need a scripted confidence label")
        frames.append(DemoFrame(t, position, radius, raw["confidence_label"], raw["track_status"]))
    if frames[0].time != 0 or frames[-1].time != duration:
        raise ValueError("First frame must be at zero and final frame at duration_seconds")
    return DemoScenario(data["scenario_name"], duration, width, height, step, tuple(frames))


def builtin_scenario(name: str) -> DemoScenario:
    if name not in BUILTINS:
        raise ValueError("Unknown demo scenario")
    return load_scenario(Path(__file__).parent/"scenarios"/BUILTINS[name])
