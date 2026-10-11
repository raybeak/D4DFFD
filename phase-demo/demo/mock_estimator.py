"""Replay positions verbatim. The normalized blob is a display fixture only."""
import numpy as np
from localization.interface import LocalizationResult, Status, validate_grid
from demo.scenario import DemoScenario


class MockEstimator:
    """Not an estimator: scenario-in/frame-out adapter to LocalizationResult.

    The optional observations argument is intentionally ignored. No observation
    values, geometry-based inference, prediction, or measurement-derived uncertainty.
    """
    def __init__(self, scenario: DemoScenario):
        self.scenario = scenario

    def estimate(self, frame_index: int, observations: object = None) -> LocalizationResult:
        if type(frame_index) is not int or not 0 <= frame_index < len(self.scenario.frames):
            raise ValueError("Invalid predefined frame index")
        s = self.scenario
        frame = s.frames[frame_index]
        if frame.position is None:
            return LocalizationResult(None, np.array([]), np.array([]), None,
                Status.INSUFFICIENT_DATA, 0, frame.time, "predefined_demo", s.grid_resolution_m,
                "PREDEFINED UI GAP - no position generated")
        step = s.grid_resolution_m
        x = (np.arange(round(s.area_width_m/step))+.5)*step
        y = (np.arange(round(s.area_height_m/step))+.5)*step
        xx, yy = np.meshgrid(x, y)
        # Pure visual convention: radius = 2 sigma of a drawn bell-shaped blob.
        # It is NOT a measured variance or a calibrated confidence region.
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            sigma = frame.uncertainty_radius/2
            log_weights = -.5*(((xx-frame.position[0])/sigma)**2+((yy-frame.position[1])/sigma)**2)
            weights = np.exp(log_weights-log_weights.max())
            grid = weights/weights.sum()
        validate_grid(grid, x, y)
        return LocalizationResult(grid, x, y, frame.position, Status.OK, 0, frame.time,
            "predefined_demo", step, "SIMULATED / PREDEFINED DATA - visual blob only")
