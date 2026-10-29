"""Open/closed eye state from raw eye openness, relative to the user's open-eye level."""

from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass

from eyeokuri.config import EyeConfig
from eyeokuri.sources import Signals


@dataclass(frozen=True)
class Observation:
    """What triggers see each frame. Gaze position will be added here later."""

    timestamp: float
    face_present: bool
    left: float | None = None
    right: float | None = None
    combined: float | None = None
    baseline: float | None = None
    ready: bool = False
    """True once enough "open" samples exist to judge closure."""
    closed: bool = False
    wink: float | None = None
    """Right eye's openness minus the left's, each relative to its own usual
    level: 0 with both open or both closed, positive = left eye closed."""
    head_yaw: float | None = None
    """Head turn in degrees relative to the user's usual pose (sign: left/right)."""
    head_pitch: float | None = None
    """Head tilt in degrees relative to the user's usual pose (positive = down)."""


class EyeStateTracker:
    """Decides open/closed relative to a rolling baseline of open-eye values."""

    def __init__(self, config: EyeConfig) -> None:
        # With close_ratio >= open_ratio, the eyes would reopen and re-close on
        # alternate frames between the two thresholds.
        # The history never spans warmup_s if the window drops samples sooner, so
        # the tracker would never become ready and blinks would never fire.
        if not 0 <= config.warmup_s < config.baseline_window_s:
            raise ValueError(
                f"eyes.warmup_s must be 0 or more and below eyes.baseline_window_s "
                f"({config.baseline_window_s}), not {config.warmup_s}"
            )
        if not 0 < config.close_ratio < config.open_ratio:
            raise ValueError(
                f"eyes.close_ratio must be above 0 and below eyes.open_ratio "
                f"({config.open_ratio}), not {config.close_ratio}"
            )
        self.config = config
        # (time, combined, left, right) while the eyes count as open.
        self._history: deque[tuple[float, float, float, float]] = deque()
        self._closed = False

    def update(self, signals: Signals) -> Observation:
        t = signals.timestamp
        if not signals.face_present:
            self._closed = False
            return Observation(t, face_present=False)
        if signals.eye_openness is None:
            # A source without eye data: head triggers still see the face.
            return Observation(t, face_present=True)

        left, right = signals.eye_openness
        # With both eyes required, the more open eye decides, so one closed
        # eye is not enough to count as "closed".
        combined = max(left, right) if self.config.require_both_eyes else min(left, right)

        baseline, ready = self._baseline(t)
        wink = None
        one_eye_closed = False
        if ready:
            # Each eye against its own usual level, so eyes that differ in size
            # (or look different at an angle) still sit near 0 when both are open.
            left_base = statistics.median(h[2] for h in self._history)
            right_base = statistics.median(h[3] for h in self._history)
            if left_base > 0 and right_base > 0:
                wink = right / right_base - left / left_base
                one_eye_closed = min(left / left_base, right / right_base) < self.config.close_ratio
        if ready:
            if self._closed:
                self._closed = combined < baseline * self.config.open_ratio
            else:
                self._closed = combined < baseline * self.config.close_ratio
        else:
            # Also recovers if the eyes looked "closed" for longer than the
            # baseline window (e.g. a big posture change): start learning again.
            self._closed = False

        # A wink isn't "closed" when both eyes must close, but learning from it
        # would pull that eye's usual level down, and with it the wink signal of
        # a long wink (holding ctrl to skip) until it fell back to 0.
        if not self._closed and not one_eye_closed:
            self._history.append((t, combined, left, right))

        return Observation(
            timestamp=t,
            face_present=True,
            left=left,
            right=right,
            combined=combined,
            baseline=baseline,
            ready=ready,
            closed=self._closed,
            wink=wink,
        )

    def _baseline(self, now: float) -> tuple[float | None, bool]:
        while self._history and now - self._history[0][0] > self.config.baseline_window_s:
            self._history.popleft()
        if not self._history:
            return None, False
        # Blinks are a small fraction of the time, so the median is a robust
        # "eyes open" level that also follows slow changes in head posture.
        baseline = statistics.median(h[1] for h in self._history)
        span = now - self._history[0][0]
        ready = span >= self.config.warmup_s and len(self._history) >= 10
        return baseline, ready
