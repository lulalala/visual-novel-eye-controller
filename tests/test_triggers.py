from vn_eye.config import HeadConfig, HeadShakeConfig, LongBlinkConfig
from vn_eye.eyes import Observation
from vn_eye.head import HeadTracker
from vn_eye.landmarks import FaceFrame
from vn_eye.outputs import ActionDispatcher
from vn_eye.triggers import HeadShakeTrigger, LongBlinkTrigger, TriggerEvent

FPS = 30


def run(trigger, segments, start=0.0):
    """segments: list of (duration_s, closed). Returns fired events."""
    events = []
    t = start
    for duration, closed in segments:
        end = t + duration
        while t < end - 1e-9:
            event = trigger.update(Observation(t, face_present=True, ready=True, closed=closed))
            if event:
                events.append(event)
            t += 1 / FPS
    return events


def test_normal_blink_does_not_fire():
    trigger = LongBlinkTrigger(LongBlinkConfig(min_duration_s=0.45))
    assert run(trigger, [(1.0, False), (0.2, True), (1.0, False)]) == []


def test_long_blink_fires_on_reopen():
    trigger = LongBlinkTrigger(LongBlinkConfig(min_duration_s=0.45))
    events = run(trigger, [(1.0, False), (0.6, True), (0.5, False)])
    assert len(events) == 1
    assert events[0].action == "next"
    assert 1.6 <= events[0].timestamp < 1.7


def test_too_long_closure_is_cancelled():
    trigger = LongBlinkTrigger(LongBlinkConfig(min_duration_s=0.45, max_duration_s=2.0))
    assert run(trigger, [(1.0, False), (3.0, True), (1.0, False)]) == []


def test_hold_mode_fires_once_while_closed():
    config = LongBlinkConfig(min_duration_s=0.45, fire_on="hold")
    trigger = LongBlinkTrigger(config)
    events = run(trigger, [(1.0, False), (3.0, True), (1.0, False)])
    assert len(events) == 1
    assert 1.0 + config.min_duration_s <= events[0].timestamp < 1.0 + config.min_duration_s + 1 / FPS


def test_losing_face_cancels_closure():
    trigger = LongBlinkTrigger(LongBlinkConfig(min_duration_s=0.45))
    run(trigger, [(1.0, False), (0.3, True)])
    trigger.update(Observation(1.31, face_present=False))
    events = run(trigger, [(0.3, True), (0.5, False)], start=1.35)
    assert events == []


def test_not_ready_ignores_closure():
    trigger = LongBlinkTrigger(LongBlinkConfig(min_duration_s=0.45))
    for i in range(30):
        assert trigger.update(Observation(i / FPS, face_present=True, ready=False, closed=True)) is None


class RecordingOutput:
    def __init__(self):
        self.sent = []

    def send(self, name):
        self.sent.append(name)


def test_dispatcher_maps_actions_and_applies_cooldown():
    out = RecordingOutput()
    dispatcher = ActionDispatcher(out, {"next": "enter"}, cooldown_s=1.0)
    assert dispatcher.dispatch(TriggerEvent("long_blink", "next", 0.0))
    assert not dispatcher.dispatch(TriggerEvent("long_blink", "next", 0.5))
    assert dispatcher.dispatch(TriggerEvent("long_blink", "next", 1.2))
    assert out.sent == ["enter", "enter"]


def test_short_and_too_long_closures_are_logged():
    messages = []
    trigger = LongBlinkTrigger(LongBlinkConfig(min_duration_s=0.45), log=messages.append)
    run(trigger, [(1.0, False), (0.2, True), (0.5, False), (3.0, True), (0.5, False)])
    assert len(messages) == 2
    assert "too short" in messages[0]
    assert "too long" in messages[1]


def test_successful_long_blink_is_not_logged_by_trigger():
    messages = []
    trigger = LongBlinkTrigger(LongBlinkConfig(min_duration_s=0.45), log=messages.append)
    assert len(run(trigger, [(1.0, False), (0.6, True), (0.5, False)])) == 1
    assert messages == []


def test_dispatcher_logs_cooldown_skips():
    messages = []
    dispatcher = ActionDispatcher(RecordingOutput(), {"next": "enter"}, 1.0, log=messages.append)
    dispatcher.dispatch(TriggerEvent("long_blink", "next", 0.0))
    dispatcher.dispatch(TriggerEvent("long_blink", "next", 0.5))
    assert len(messages) == 1 and "cooldown" in messages[0]


def test_blink_with_head_turned_is_ignored():
    messages = []
    trigger = LongBlinkTrigger(LongBlinkConfig(min_duration_s=0.15), log=messages.append)
    obs = [Observation(i / FPS, face_present=True, ready=True, closed=8 <= i < 16, head_yaw=20.0 if i == 10 else 2.0)
           for i in range(30)]
    assert [e for o in obs if (e := trigger.update(o))] == []
    assert "head turned" in messages[0]


def shake(trigger, yaws, start=0.0):
    events = []
    for i, yaw in enumerate(yaws):
        event = trigger.update(Observation(start + i / FPS, face_present=True, head_yaw=yaw))
        if event:
            events.append(event)
    return events


def sweep(a, b, frames):
    return [a + (b - a) * i / frames for i in range(frames)]


def test_head_shake_left_right_fires():
    trigger = HeadShakeTrigger(HeadShakeConfig())
    yaws = [0.0] * 10 + sweep(0, -25, 6) + sweep(-25, 25, 10) + sweep(25, 0, 6) + [0.0] * 10
    events = shake(trigger, yaws)
    assert len(events) == 1 and events[0].action == "toggle_pause"


def test_head_shake_right_left_fires_too():
    trigger = HeadShakeTrigger(HeadShakeConfig())
    yaws = [0.0] * 10 + sweep(0, 25, 6) + sweep(25, -25, 10) + sweep(-25, 0, 6)
    assert len(shake(trigger, yaws)) == 1


def test_single_turn_does_not_fire():
    trigger = HeadShakeTrigger(HeadShakeConfig())
    yaws = [0.0] * 10 + sweep(0, -30, 6) + [-30.0] * 30 + sweep(-30, 0, 6) + [0.0] * 10
    assert shake(trigger, yaws) == []


def test_slow_look_left_then_right_does_not_fire():
    trigger = HeadShakeTrigger(HeadShakeConfig(max_duration_s=1.0))
    # Look left for 2 s, then swing quickly right: the left turn started too long ago.
    yaws = [0.0] * 10 + [-25.0] * 60 + sweep(-25, 25, 6) + [25.0] * 10
    assert shake(trigger, yaws) == []


def test_head_shake_cooldown_blocks_continued_shaking():
    trigger = HeadShakeTrigger(HeadShakeConfig(cooldown_s=1.5))
    one = sweep(0, -25, 4) + sweep(-25, 25, 6) + sweep(25, 0, 4)
    assert len(shake(trigger, [0.0] * 5 + one + one)) == 1


def test_head_tracker_is_relative_to_usual_pose():
    tracker = HeadTracker(HeadConfig())
    for i in range(60):
        tracker.update(FaceFrame(i / FPS, None, head_yaw_deg=10.0))
    assert tracker.update(FaceFrame(2.0, None, head_yaw_deg=35.0)) == 25.0
