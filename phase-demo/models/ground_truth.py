from dataclasses import dataclass


@dataclass(frozen=True)
class GroundTruth:
    timestamp: float
    emitter_id: str
    x: float
    y: float
