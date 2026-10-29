import math

import numpy as np
import pytest

from eyeokuri.sources.face_mesh import crop_transform, detector_anchors, head_pose_from_landmarks

RIGHT_EYE_OUTER, LEFT_EYE_OUTER, FOREHEAD, CHIN = 33, 263, 10, 152


def make_head(yaw_deg: float = 0.0, pitch_deg: float = 0.0, roll_deg: float = 0.0) -> np.ndarray:
    """A fake 478-point mesh in image axes (x right, y down, z away from the camera)
    with only the head-axis points set, tilted sideways by roll, then tilted by
    pitch and turned by yaw."""
    points = np.zeros((478, 3))
    points[RIGHT_EYE_OUTER] = (-30, 0, 0)
    points[LEFT_EYE_OUTER] = (30, 0, 0)
    points[FOREHEAD] = (0, -60, 0)
    points[CHIN] = (0, 60, 0)
    y, p, r = math.radians(yaw_deg), math.radians(pitch_deg), math.radians(roll_deg)
    # Positive yaw swings the face toward +x; positive pitch tilts the chin away
    # (head down); positive roll swings the forehead toward +x.
    turn = np.array([[math.cos(y), 0, -math.sin(y)], [0, 1, 0], [math.sin(y), 0, math.cos(y)]])
    tilt = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])
    lean = np.array([[math.cos(r), -math.sin(r), 0], [math.sin(r), math.cos(r), 0], [0, 0, 1]])
    return points @ (turn @ tilt @ lean).T + (320, 240, 500)


def test_frontal_head_has_zero_pose():
    yaw, pitch, roll = head_pose_from_landmarks(make_head())
    assert yaw == pytest.approx(0.0, abs=1e-6)
    assert pitch == pytest.approx(0.0, abs=1e-6)
    assert roll == pytest.approx(0.0, abs=1e-6)


def test_head_tilted_down_has_positive_pitch():
    yaw, pitch, roll = head_pose_from_landmarks(make_head(pitch_deg=20))
    assert pitch == pytest.approx(20.0)
    assert yaw == pytest.approx(0.0, abs=1e-6)
    assert roll == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("angle", [-30.0, -10.0, 15.0, 30.0])
def test_head_turn_is_recovered_in_degrees(angle):
    yaw, pitch, roll = head_pose_from_landmarks(make_head(yaw_deg=angle))
    assert yaw == pytest.approx(angle)
    assert pitch == pytest.approx(0.0, abs=1e-6)
    assert roll == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("angle", [-25.0, -10.0, 15.0, 25.0])
def test_sideways_tilt_is_recovered_in_degrees(angle):
    yaw, pitch, roll = head_pose_from_landmarks(make_head(roll_deg=angle))
    assert roll == pytest.approx(angle)
    assert yaw == pytest.approx(0.0, abs=1e-6)
    assert pitch == pytest.approx(0.0, abs=1e-6)


def test_sideways_tilt_survives_a_turn():
    _, _, roll = head_pose_from_landmarks(make_head(yaw_deg=30, roll_deg=20))
    assert roll == pytest.approx(20.0)


def test_tilt_toward_your_left_shoulder_is_positive_roll():
    # The image isn't mirrored, so your left shoulder is on the image's right,
    # and your left eye corner (also on the image's right) drops.
    points = make_head()
    points[LEFT_EYE_OUTER, 1] += 10
    points[RIGHT_EYE_OUTER, 1] -= 10
    assert head_pose_from_landmarks(points)[2] > 0


def test_anchors_cover_both_detector_grids():
    anchors = detector_anchors()
    assert anchors.shape == (896, 2)
    assert anchors[0] == pytest.approx((1 / 32, 1 / 32))
    assert anchors[-1] == pytest.approx((15 / 16, 15 / 16))
    assert ((anchors > 0) & (anchors < 1)).all()


def test_crop_transform_maps_crop_center_and_scale():
    m = crop_transform((400.0, 300.0), 512.0, 0.0, 256)
    assert m @ (128, 128, 1) == pytest.approx((400.0, 300.0))
    assert m @ (256, 128, 1) == pytest.approx((656.0, 300.0))


def test_crop_transform_follows_face_rotation():
    # A face rolled 90° clockwise in the frame: the crop's x axis runs down the frame.
    m = crop_transform((400.0, 300.0), 256.0, math.pi / 2, 256)
    assert m @ (228, 128, 1) == pytest.approx((400.0, 400.0), abs=1e-4)
