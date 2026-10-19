"""Signal sources: what a source measures, and the interface every source implements.

A source owns its input (webcam, eye tracker, ...) and reports raw measurements
as ``Signals``. The core adapts them to the user and feeds the triggers, so
camera frames never leave the source.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

EYE_OPENNESS = "eye_openness"
HEAD_POSE = "head_pose"


@dataclass(frozen=True)
class Signals:
    """What a source measured at one moment. A source fills only what it provides."""

    timestamp: float
    """Seconds, from time.monotonic()."""
    face_present: bool
    eye_openness: tuple[float, float] | None = None
    """(left, right) from the subject's view. 0 = fully closed; larger = more open.
    Any scale, as long as it is proportional, because "closed" is a ratio of the
    open-eye baseline."""
    head_yaw_deg: float | None = None
    """Absolute head turn. Positive = face turned toward the image's right."""
    head_pitch_deg: float | None = None
    """Absolute head tilt. Positive = head tilted down."""


class Source(Protocol):
    name: str
    provides: frozenset[str]
    """Signal names this source can fill, e.g. frozenset({EYE_OPENNESS, HEAD_POSE})."""

    def read(self) -> Signals:
        """Block until the next sample, for at most about 0.1 s. Return
        ``Signals(t, face_present=False)`` when there is no face or no data."""
        ...

    def debug_view(self) -> np.ndarray | None:
        """BGR image for the preview window, or None if the source has nothing to show."""
        ...

    def close(self) -> None: ...
