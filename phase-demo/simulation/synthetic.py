"""SYNTHETIC DATA: arbitrary scalars, no RF or position information."""
import numpy as np
from models.observation import Observation
from models.receiver import Receiver


def generate_observations(receivers: tuple[Receiver, ...], emitter_id: str, *,
                          seed: int, timestamp: float, noise: float,
                          bias: float, dropout: float, base_value: float) -> tuple[Observation, ...]:
    """Does not accept, read, or encode emitter ground truth."""
    rng = np.random.default_rng(seed)
    observations = []
    for receiver in receivers:
        # Draw for all receivers so disabling one does not shift other draws.
        missing = rng.random() < dropout
        value = float(base_value + bias + rng.normal(0, noise))
        if receiver.enabled and not missing:
            observations.append(Observation(timestamp, receiver.receiver_id, emitter_id, value))
    return tuple(observations)
