from dataclasses import dataclass


@dataclass(frozen=True)
class Receiver:
    receiver_id: str
    x: float
    y: float
    enabled: bool = True
