import numpy as np
import pytest

from vn_eye.config import EyeConfig
from vn_eye.eyes import LEFT_EYE, RIGHT_EYE, EyeStateTracker, eye_aspect_ratio
from vn_eye.landmarks import FaceFrame


def make_face(t: float, openness: float, right: float | None = None) -> FaceFrame:
    """A fake 478-point face whose eyes have the given EAR values."""
    points = np.zeros((478, 3), dtype=np.float32)
    for idx, ear, x0 in ((LEFT_EYE, openness, 300.0), (RIGHT_EYE, right if right is not None else openness, 100.0)):
        width = 60.0
        half = ear * width / 2.0
        p1, p2, p3, p4, p5, p6 = idx
        points[p1] = (x0, 200, 0)
        points[p4] = (x0 + width, 200, 0)
        points[p2] = (x0 + 20, 200 - half, 0)
        points[p6] = (x0 + 20, 200 + half, 0)
        points[p3] = (x0 + 40, 200 - half, 0)
        points[p5] = (x0 + 40, 200 + half, 0)
    return FaceFrame(t, points)


def test_eye_aspect_ratio_matches_construction():
    face = make_face(0.0, 0.3, right=0.1)
    assert eye_aspect_ratio(face.landmarks, LEFT_EYE) == pytest.approx(0.3)
    assert eye_aspect_ratio(face.landmarks, RIGHT_EYE) == pytest.approx(0.1)


def feed(tracker, start, end, openness, fps=30, right=None):
    obs = []
    t = start
    while t < end - 1e-9:
        obs.append(tracker.update(make_face(t, openness, right)))
        t += 1 / fps
    return obs


def test_not_ready_until_warmup():
    tracker = EyeStateTracker(EyeConfig(warmup_s=2.0))
    obs = feed(tracker, 0.0, 1.0, 0.3)
    assert not any(o.ready for o in obs)
    obs = feed(tracker, 1.0, 2.5, 0.3)
    assert obs[-1].ready
    assert obs[-1].baseline == pytest.approx(0.3)


def test_closed_with_hysteresis():
    tracker = EyeStateTracker(EyeConfig())
    feed(tracker, 0.0, 3.0, 0.30)
    assert feed(tracker, 3.0, 3.1, 0.10)[-1].closed
    # Between close (0.165) and open (0.225) thresholds: stays closed.
    assert feed(tracker, 3.1, 3.2, 0.20)[-1].closed
    assert not feed(tracker, 3.2, 3.3, 0.28)[-1].closed


def test_one_eye_closed_is_not_closed_when_both_required():
    tracker = EyeStateTracker(EyeConfig(require_both_eyes=True))
    feed(tracker, 0.0, 3.0, 0.30)
    assert not feed(tracker, 3.0, 3.5, 0.05, right=0.30)[-1].closed


def test_no_face_resets_closed_state():
    tracker = EyeStateTracker(EyeConfig())
    feed(tracker, 0.0, 3.0, 0.30)
    assert feed(tracker, 3.0, 3.1, 0.05)[-1].closed
    obs = tracker.update(FaceFrame(3.2, None))
    assert not obs.face_present and not obs.closed
