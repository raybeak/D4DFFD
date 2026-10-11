from dataclasses import dataclass


@dataclass(frozen=True)
class Observation:
    timestamp: float
    receiver_id: str
    emitter_id: str
    value: float
    unit: str = "synthetic_unit"
    quality: str = "VALID"
