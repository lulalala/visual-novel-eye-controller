import pytest

from eyeokuri.config import EyeConfig
from eyeokuri.eyes import EyeStateTracker
from eyeokuri.sources import Signals


def feed(tracker, start, end, openness, fps=30, right=None):
    obs = []
    t = start
    while t < end - 1e-9:
        eyes = (openness, right if right is not None else openness)
        obs.append(tracker.update(Signals(t, face_present=True, eye_openness=eyes)))
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
    obs = tracker.update(Signals(3.2, face_present=False))
    assert not obs.face_present and not obs.closed


def test_face_without_eye_data_is_present_but_never_ready():
    tracker = EyeStateTracker(EyeConfig())
    obs = [tracker.update(Signals(i / 30, face_present=True)) for i in range(90)]
    assert all(o.face_present and not o.ready and not o.closed for o in obs)


def test_any_proportional_scale_works():
    # A source reporting 0..1 openness instead of EAR values closes the same way.
    tracker = EyeStateTracker(EyeConfig())
    feed(tracker, 0.0, 3.0, 1.0)
    assert feed(tracker, 3.0, 3.1, 0.3)[-1].closed


@pytest.mark.parametrize("close_ratio, open_ratio", [(0.75, 0.75), (0.8, 0.75), (0.0, 0.75)])
def test_inverted_or_empty_hysteresis_is_rejected(close_ratio, open_ratio):
    with pytest.raises(ValueError, match="eyes.close_ratio"):
        EyeStateTracker(EyeConfig(close_ratio=close_ratio, open_ratio=open_ratio))
