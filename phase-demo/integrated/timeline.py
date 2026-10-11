"""One logical clock; wall time is supplied only by the UI adapter."""
from telemetry.schema import number


class Timeline:
    def __init__(self, duration, speed=1.):
        if not number(duration) or duration <= 0:
            raise ValueError('Integrated duration must be finite and positive')
        self.duration = float(duration)
        self.set_speed(speed)
        self.reset()

    def set_speed(self, speed):
        if not number(speed) or speed not in (.5, 1., 2.):
            raise ValueError('Integrated speed must be 0.5, 1 or 2')
        self.speed = float(speed)

    def reset(self):
        self.time = 0.
        self.playing = False

    def play(self):
        self.playing = self.time < self.duration

    def pause(self):
        self.playing = False

    def seek(self, t):
        if not number(t) or not 0 <= t <= self.duration:
            raise ValueError(f'Seek time must be within [0, {self.duration}]')
        self.time = float(t)
        if self.time == self.duration:
            self.pause()

    def advance(self, seconds):
        if not number(seconds) or seconds < 0:
            raise ValueError('Elapsed time must be finite and nonnegative')
        if self.playing:
            self.seek(min(self.duration, self.time + seconds * self.speed))
        return self.time
