"""Eye openness from face landmarks, with an adaptive open/closed decision."""

from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass

import numpy as np

from vn_eye.config import EyeConfig
from vn_eye.landmarks import FaceFrame

# MediaPipe Face Mesh indices, ordered p1..p6 for the eye aspect ratio:
# p1/p4 are the eye corners, (p2, p6) and (p3, p5) are upper/lower lid pairs.
# "Left"/"right" are from the subject's point of view.
LEFT_EYE = (362, 385, 387, 263, 373, 380)
RIGHT_EYE = (33, 160, 158, 133, 153, 144)


def eye_aspect_ratio(points: np.ndarray, idx: tuple[int, ...]) -> float:
    """Soukupová & Čech (2016) EAR: ~0.25-0.35 when open, near 0 when closed."""
    p = points[list(idx), :2]
    vertical = np.linalg.norm(p[1] - p[5]) + np.linalg.norm(p[2] - p[4])
    horizontal = np.linalg.norm(p[0] - p[3])
    if horizontal < 1e-6:
        return 0.0
    return float(vertical / (2.0 * horizontal))


def eye_openness(face: FaceFrame, metric: str) -> tuple[float, float] | None:
    """(left, right) openness; larger means more open. None if no face."""
    if face.landmarks is None:
        return None
    if metric == "ear":
        return (
            eye_aspect_ratio(face.landmarks, LEFT_EYE),
            eye_aspect_ratio(face.landmarks, RIGHT_EYE),
        )
    if metric == "blendshape":
        if not face.blendshapes:
            return None
        return (
            1.0 - face.blendshapes.get("eyeBlinkLeft", 0.0),
            1.0 - face.blendshapes.get("eyeBlinkRight", 0.0),
        )
    raise ValueError(f"Unknown eye metric: {metric}")


@dataclass(frozen=True)
class EyeObservation:
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


class EyeStateTracker:
    """Decides open/closed relative to a rolling baseline of open-eye values."""

    def __init__(self, config: EyeConfig) -> None:
        self.config = config
        self._history: deque[tuple[float, float]] = deque()
        self._closed = False

    def reset(self) -> None:
        self._history.clear()
        self._closed = False

    def update(self, face: FaceFrame) -> EyeObservation:
        values = eye_openness(face, self.config.metric)
        t = face.timestamp
        if values is None:
            self._closed = False
            return EyeObservation(t, face_present=False)

        left, right = values
        # With both eyes required, the more open eye decides, so one closed
        # eye is not enough to count as "closed".
        combined = max(left, right) if self.config.require_both_eyes else min(left, right)

        baseline, ready = self._baseline(t)
        if ready:
            if self._closed:
                self._closed = combined < baseline * self.config.open_ratio
            else:
                self._closed = combined < baseline * self.config.close_ratio
        else:
            # Also recovers if the eyes looked "closed" for longer than the
            # baseline window (e.g. a big posture change): start learning again.
            self._closed = False

        if not self._closed:
            self._history.append((t, combined))

        return EyeObservation(
            timestamp=t,
            face_present=True,
            left=left,
            right=right,
            combined=combined,
            baseline=baseline,
            ready=ready,
            closed=self._closed,
        )

    def _baseline(self, now: float) -> tuple[float | None, bool]:
        while self._history and now - self._history[0][0] > self.config.baseline_window_s:
            self._history.popleft()
        if not self._history:
            return None, False
        # Blinks are a small fraction of the time, so the median is a robust
        # "eyes open" level that also follows slow changes in head posture.
        baseline = statistics.median(v for _, v in self._history)
        span = now - self._history[0][0]
        ready = span >= self.config.warmup_s and len(self._history) >= 10
        return baseline, ready
