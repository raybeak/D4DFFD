"""Strict wire schema. Times are seconds on a shared synthetic clock."""
from dataclasses import dataclass, asdict
from enum import Enum
import math


class Quality(str, Enum):
    GOOD = 'GOOD'
    BAD = 'BAD'


class Health(str, Enum):
    HEALTHY = 'HEALTHY'
    DEGRADED = 'DEGRADED'
    OFFLINE = 'OFFLINE'
    RECOVERING = 'RECOVERING'


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


@dataclass(frozen=True)
class Message:
    sensor_id: str
    timestamp: float
    sequence_number: int
    measurement_value: float
    quality_flag: str

    def __post_init__(self):
        if type(self.sensor_id) is not str or not self.sensor_id.strip():
            raise ValueError('sensor_id must be a nonempty string')
        if not number(self.timestamp) or self.timestamp < 0:
            raise ValueError('timestamp must be finite and nonnegative')
        if type(self.sequence_number) is not int or self.sequence_number < 0:
            raise ValueError('sequence_number must be a nonnegative integer')
        if not number(self.measurement_value):
            raise ValueError('measurement_value must be a finite real number')
        if self.quality_flag not in ('GOOD', 'BAD') or type(self.quality_flag) is not str:
            raise ValueError('quality_flag must be GOOD or BAD')

    @classmethod
    def parse(cls, raw):
        if type(raw) is not dict or set(raw) != set(cls.__dataclass_fields__):
            raise ValueError('message must contain exactly the five schema fields')
        try:
            return cls(**raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(str(exc)) from exc

    def to_dict(self):
        return asdict(self)
