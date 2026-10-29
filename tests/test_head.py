import pytest

from eyeokuri.config import HeadConfig
from eyeokuri.head import HeadTracker
from eyeokuri.sources import Signals


def feed(tracker, start, end, yaw, fps=30, roll=0.0):
    out = []
    t = start
    while t < end - 1e-9:
        out.append(tracker.update(Signals(t, face_present=True, head_yaw_deg=yaw, head_pitch_deg=0.0,
                                          head_roll_deg=roll)))
        t += 1 / fps
    return out


def test_no_head_pose_until_warmup():
    tracker = HeadTracker(HeadConfig(warmup_s=2.0))
    assert all(r == (None, None, None) for r in feed(tracker, 0.0, 1.0, 20.0))
    yaw, pitch, roll = feed(tracker, 1.0, 2.5, 20.0)[-1]
    assert yaw == 0.0 and pitch == 0.0 and roll == 0.0


def test_head_pose_is_relative_to_the_resting_pose_after_warmup():
    tracker = HeadTracker(HeadConfig(warmup_s=2.0))
    feed(tracker, 0.0, 3.0, 5.0)
    yaw, _, _ = feed(tracker, 3.0, 3.05, 25.0)[-1]
    assert yaw == 20.0


def test_warmup_starts_again_after_a_long_face_loss():
    tracker = HeadTracker(HeadConfig(warmup_s=2.0, baseline_window_s=10.0))
    feed(tracker, 0.0, 3.0, 0.0)
    assert feed(tracker, 30.0, 30.5, 0.0)[-1] == (None, None, None)


def test_head_warmup_longer_than_the_window_is_rejected():
    with pytest.raises(ValueError, match="head.warmup_s"):
        HeadTracker(HeadConfig(warmup_s=10.0, baseline_window_s=10.0))


@pytest.mark.parametrize("fps", [10, 30])
def test_long_sideways_tilt_keeps_its_roll(fps):
    # Holding a tilt (to hold ctrl) longer than half the window, where the median would flip.
    tracker = HeadTracker(HeadConfig(warmup_s=2.0, baseline_window_s=10.0))
    feed(tracker, 0.0, 3.0, 0.0, fps=fps, roll=2.0)
    rolls = [r for _, _, r in feed(tracker, 3.0, 12.0, 0.0, fps=fps, roll=-18.0)]
    assert all(r == -20.0 for r in rolls)


def test_slow_sideways_drift_is_still_learned():
    tracker = HeadTracker(HeadConfig(warmup_s=2.0, baseline_window_s=10.0))
    feed(tracker, 0.0, 3.0, 0.0)
    feed(tracker, 3.0, 20.0, 0.0, roll=6.0)
    assert feed(tracker, 20.0, 20.1, 0.0, roll=6.0)[-1][2] == 0.0


def test_tilt_held_past_the_window_is_learned_again():
    tracker = HeadTracker(HeadConfig(warmup_s=2.0, baseline_window_s=10.0))
    feed(tracker, 0.0, 3.0, 0.0)
    rolls = [r for _, _, r in feed(tracker, 3.0, 20.0, 0.0, roll=-20.0)]
    # No roll while it learns the tilted pose, which ends a gesture in progress.
    assert None in rolls
    assert rolls[-1] == 0.0
