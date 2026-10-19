"""Head pose relative to the user's usual pose."""

from __future__ import annotations

import statistics
from collections import deque

from vn_eye.config import HeadConfig
from vn_eye.sources import Signals


class HeadTracker:
    """Reports head yaw and pitch relative to a rolling median, so an
    off-center webcam or a habitual slight tilt reads as 0."""

    def __init__(self, config: HeadConfig) -> None:
        # A zero or negative window drops every sample, including the newest.
        if config.baseline_window_s <= 0:
            raise ValueError(f"head.baseline_window_s must be above 0, not {config.baseline_window_s}")
        self.config = config
        self._yaw_history: deque[tuple[float, float]] = deque()
        self._pitch_history: deque[tuple[float, float]] = deque()

    def update(self, signals: Signals) -> tuple[float | None, float | None]:
        t = signals.timestamp
        yaw = self._relative(self._yaw_history, t, signals.head_yaw_deg)
        pitch = self._relative(self._pitch_history, t, signals.head_pitch_deg)
        return yaw, pitch

    def _relative(
        self, history: deque[tuple[float, float]], t: float, value: float | None
    ) -> float | None:
        if value is None:
            return None
        history.append((t, value))
        while t - history[0][0] > self.config.baseline_window_s:
            history.popleft()
        # Brief turns barely move the median, so it stays close to the resting pose.
        return value - statistics.median(v for _, v in history)
