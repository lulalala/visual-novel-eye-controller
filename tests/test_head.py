import pytest

from eyeokuri.config import HeadConfig
from eyeokuri.head import HeadTracker
from eyeokuri.sources import Signals


def feed(tracker, start, end, yaw, fps=30):
    out = []
    t = start
    while t < end - 1e-9:
        out.append(tracker.update(Signals(t, face_present=True, head_yaw_deg=yaw, head_pitch_deg=0.0)))
        t += 1 / fps
    return out


def test_no_head_pose_until_warmup():
    tracker = HeadTracker(HeadConfig(warmup_s=2.0))
    assert all(r == (None, None) for r in feed(tracker, 0.0, 1.0, 20.0))
    yaw, pitch = feed(tracker, 1.0, 2.5, 20.0)[-1]
    assert yaw == 0.0 and pitch == 0.0


def test_head_pose_is_relative_to_the_resting_pose_after_warmup():
    tracker = HeadTracker(HeadConfig(warmup_s=2.0))
    feed(tracker, 0.0, 3.0, 5.0)
    yaw, _ = feed(tracker, 3.0, 3.05, 25.0)[-1]
    assert yaw == 20.0


def test_warmup_starts_again_after_a_long_face_loss():
    tracker = HeadTracker(HeadConfig(warmup_s=2.0, baseline_window_s=10.0))
    feed(tracker, 0.0, 3.0, 0.0)
    assert feed(tracker, 30.0, 30.5, 0.0)[-1] == (None, None)


def test_head_warmup_longer_than_the_window_is_rejected():
    with pytest.raises(ValueError, match="head.warmup_s"):
        HeadTracker(HeadConfig(warmup_s=10.0, baseline_window_s=10.0))
