import numpy as np
import pytest

from vn_eye.sources import EYE_OPENNESS, HEAD_POSE
from vn_eye.sources.opencv import LEFT_EYE, RIGHT_EYE, OpenCVSource, eye_aspect_ratio, signals_from_landmarks

RIGHT_EYE_OUTER, LEFT_EYE_OUTER, FOREHEAD, CHIN = 33, 263, 10, 152


def make_face(left: float, right: float) -> np.ndarray:
    """A fake frontal 478-point mesh whose eyes have the given EAR values."""
    points = np.zeros((478, 3), dtype=np.float32)
    for idx, ear, x0 in ((LEFT_EYE, left, 300.0), (RIGHT_EYE, right, 100.0)):
        width = 60.0
        half = ear * width / 2.0
        p1, p2, p3, p4, p5, p6 = idx
        points[p1] = (x0, 200, 0)
        points[p4] = (x0 + width, 200, 0)
        points[p2] = (x0 + 20, 200 - half, 0)
        points[p6] = (x0 + 20, 200 + half, 0)
        points[p3] = (x0 + 40, 200 - half, 0)
        points[p5] = (x0 + 40, 200 + half, 0)
    # Head axes: outer eye corners level, forehead straight above the chin.
    points[RIGHT_EYE_OUTER] = (100, 200, 0)
    points[LEFT_EYE_OUTER] = (360, 200, 0)
    points[FOREHEAD] = (230, 80, 0)
    points[CHIN] = (230, 400, 0)
    return points


def test_eye_aspect_ratio_matches_construction():
    face = make_face(0.3, 0.1)
    assert eye_aspect_ratio(face, LEFT_EYE) == pytest.approx(0.3)
    assert eye_aspect_ratio(face, RIGHT_EYE) == pytest.approx(0.1)


def test_landmarks_become_eye_openness_and_head_pose():
    signals = signals_from_landmarks(1.5, make_face(0.3, 0.25))
    assert signals.timestamp == 1.5
    assert signals.face_present
    assert signals.eye_openness == pytest.approx((0.3, 0.25))
    assert signals.head_yaw_deg == pytest.approx(0.0, abs=1e-6)
    assert signals.head_pitch_deg == pytest.approx(0.0, abs=1e-6)


def test_no_landmarks_means_no_face():
    signals = signals_from_landmarks(2.0, None)
    assert not signals.face_present
    assert signals.eye_openness is None
    assert signals.head_yaw_deg is None


def test_source_provides_eyes_and_head_pose():
    assert OpenCVSource.provides == {EYE_OPENNESS, HEAD_POSE}
