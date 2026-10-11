"""Deterministic UI playback; no interpolation, extrapolation, or tracking."""
from bisect import bisect_right
from collections import deque
import math
from demo.scenario import DemoScenario, DemoFrame


class DemoPlayer:
    def __init__(self, scenario: DemoScenario, speed: float = 1., history_length: int = 15):
        if type(history_length) is not int or history_length < 1:
            raise ValueError("history_length must be a positive integer")
        self.scenario = scenario
        self.times = tuple(frame.time for frame in scenario.frames)
        self.history = deque(maxlen=history_length)
        self.set_speed(speed)
        self.reset()

    @property
    def current_frame(self) -> DemoFrame:
        return self.scenario.frames[self.frame_index]

    def set_speed(self, speed: float) -> None:
        if speed not in (.5, 1., 2.) or isinstance(speed, bool):
            raise ValueError("Demo speed must be 0.5, 1, or 2")
        self.speed = float(speed)

    def reset(self) -> None:
        self.elapsed = 0.
        self.frame_index = 0
        self.playing = False
        self.history.clear()
        self.history.append(self.current_frame)

    def play(self) -> None:
        if self.elapsed < self.scenario.duration_seconds:
            self.playing = True

    def pause(self) -> None:
        self.playing = False

    def advance(self, wall_seconds: float) -> None:
        if not math.isfinite(wall_seconds) or wall_seconds < 0:
            raise ValueError("Elapsed wall time must be finite and nonnegative")
        if not self.playing:
            return
        self.seek(min(self.elapsed+wall_seconds*self.speed, self.scenario.duration_seconds))
        if self.elapsed >= self.scenario.duration_seconds:
            self.pause()

    def seek(self, elapsed: float) -> None:
        """Show latest authored frame at/before time; no invented in-between point."""
        if not math.isfinite(elapsed) or not 0 <= elapsed <= self.scenario.duration_seconds:
            raise ValueError("Time outside scenario")
        self.elapsed = float(elapsed)
        self.frame_index = bisect_right(self.times, elapsed)-1
        self.history.clear()
        start = max(0, self.frame_index-self.history.maxlen+1)
        self.history.extend(self.scenario.frames[start:self.frame_index+1])
