"""Head yaw relative to the user's usual pose."""

from __future__ import annotations

import statistics
from collections import deque

from vn_eye.config import HeadConfig
from vn_eye.landmarks import FaceFrame


class HeadTracker:
    """Reports head yaw relative to a rolling median, so an off-centre webcam
    or a habitual slight turn reads as 0."""

    def __init__(self, config: HeadConfig) -> None:
        self.config = config
        self._history: deque[tuple[float, float]] = deque()

    def update(self, face: FaceFrame) -> float | None:
        if face.head_yaw_deg is None:
            return None
        t = face.timestamp
        self._history.append((t, face.head_yaw_deg))
        while t - self._history[0][0] > self.config.baseline_window_s:
            self._history.popleft()
        # Brief turns (a head shake, a glance away) barely move the median.
        return face.head_yaw_deg - statistics.median(v for _, v in self._history)
