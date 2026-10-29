"""Head pose relative to the user's usual pose."""

from __future__ import annotations

import statistics
from collections import deque

from eyeokuri.config import HeadConfig
from eyeokuri.sources import Signals


# A sideways tilt further than this from the usual pose isn't learned from:
# holding a tilt (to hold ctrl and skip) would otherwise teach the tracker
# that the tilt is your usual pose, and after about half the window the
# roll would fall back to 0 with your head still tilted.
_ROLL_LEARN_DEG = 8.0


class HeadTracker:
    """Reports head yaw, pitch and roll relative to a rolling median, so an
    off-center webcam or a habitual slight tilt reads as 0."""

    def __init__(self, config: HeadConfig) -> None:
        # A zero or negative window drops every sample, including the newest.
        if config.baseline_window_s <= 0:
            raise ValueError(f"head.baseline_window_s must be above 0, not {config.baseline_window_s}")
        if not 0 <= config.warmup_s < config.baseline_window_s:
            raise ValueError(
                f"head.warmup_s must be 0 or more and below head.baseline_window_s "
                f"({config.baseline_window_s}), not {config.warmup_s}"
            )
        self.config = config
        self._yaw_history: deque[tuple[float, float]] = deque()
        self._pitch_history: deque[tuple[float, float]] = deque()
        self._roll_history: deque[tuple[float, float]] = deque()

    def update(self, signals: Signals) -> tuple[float | None, float | None, float | None]:
        t = signals.timestamp
        yaw = self._relative(self._yaw_history, t, signals.head_yaw_deg)
        pitch = self._relative(self._pitch_history, t, signals.head_pitch_deg)
        roll = self._relative(self._roll_history, t, signals.head_roll_deg, _ROLL_LEARN_DEG)
        return yaw, pitch, roll

    def _relative(
        self, history: deque[tuple[float, float]], t: float, value: float | None,
        learn_within_deg: float | None = None,
    ) -> float | None:
        if value is None:
            return None
        while history and t - history[0][0] > self.config.baseline_window_s:
            history.popleft()
        if learn_within_deg is not None and history and t - history[0][0] >= self.config.warmup_s:
            relative = value - statistics.median(v for _, v in history)
            if abs(relative) > learn_within_deg:
                # Held longer than the window, the history runs out and the
                # tracker learns again from the new pose, after warmup_s.
                return relative
        history.append((t, value))
        # With almost no history the median is the current pose, so every pose
        # would read as 0. None cancels any half-done gesture.
        if t - history[0][0] < self.config.warmup_s:
            return None
        # Brief turns barely move the median, so it stays close to the resting pose.
        return value - statistics.median(v for _, v in history)
