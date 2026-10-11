from dataclasses import dataclass


@dataclass(frozen=True)
class Emitter:
    emitter_id: str
    emitter_type: str = "COOPERATIVE_SYNTHETIC_TEST"
