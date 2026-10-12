from vn_eye.config import BlinkConfig, Config, HeadConfig, HeadShakeConfig, NodConfig
from vn_eye.eyes import Observation
from vn_eye.head import HeadTracker
from vn_eye.sources import EYE_OPENNESS, HEAD_POSE, Signals
from vn_eye.outputs import ActionDispatcher
from vn_eye.triggers import (
    BlinkTrigger,
    HeadShakeTrigger,
    NodTrigger,
    TriggerEvent,
    create_triggers,
    supported_triggers,
)

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
    trigger = BlinkTrigger(BlinkConfig(min_duration_s=0.45))
    assert run(trigger, [(1.0, False), (0.2, True), (1.0, False)]) == []


def test_blink_fires_on_reopen():
    trigger = BlinkTrigger(BlinkConfig(min_duration_s=0.45))
    events = run(trigger, [(1.0, False), (0.6, True), (0.5, False)])
    assert len(events) == 1
    assert events[0].action == "blink"
    assert 1.6 <= events[0].timestamp < 1.7


def test_too_long_closure_is_canceled():
    trigger = BlinkTrigger(BlinkConfig(min_duration_s=0.45, max_duration_s=2.0))
    assert run(trigger, [(1.0, False), (3.0, True), (1.0, False)]) == []


def test_losing_face_cancels_closure():
    trigger = BlinkTrigger(BlinkConfig(min_duration_s=0.45))
    run(trigger, [(1.0, False), (0.3, True)])
    trigger.update(Observation(1.31, face_present=False))
    events = run(trigger, [(0.3, True), (0.5, False)], start=1.35)
    assert events == []


def test_not_ready_ignores_closure():
    trigger = BlinkTrigger(BlinkConfig(min_duration_s=0.45))
    for i in range(30):
        assert trigger.update(Observation(i / FPS, face_present=True, ready=False, closed=True)) is None


class RecordingOutput:
    def __init__(self):
        self.sent = []

    def send(self, name):
        self.sent.append(name)


def test_dispatcher_maps_actions_and_applies_cooldown():
    out = RecordingOutput()
    dispatcher = ActionDispatcher(out, {"blink": "enter"}, cooldown_s=1.0)
    assert dispatcher.dispatch(TriggerEvent("blink", "blink", 0.0))
    assert not dispatcher.dispatch(TriggerEvent("blink", "blink", 0.5))
    assert dispatcher.dispatch(TriggerEvent("blink", "blink", 1.2))
    assert out.sent == ["enter", "enter"]


def test_short_and_too_long_closures_are_logged():
    messages = []
    trigger = BlinkTrigger(BlinkConfig(min_duration_s=0.45), log=messages.append)
    run(trigger, [(1.0, False), (0.2, True), (0.5, False), (3.0, True), (0.5, False)])
    assert len(messages) == 2
    assert "too short" in messages[0]
    assert "too long" in messages[1]


def test_successful_blink_is_not_logged_by_trigger():
    messages = []
    trigger = BlinkTrigger(BlinkConfig(min_duration_s=0.45), log=messages.append)
    assert len(run(trigger, [(1.0, False), (0.6, True), (0.5, False)])) == 1
    assert messages == []


def test_dispatcher_logs_cooldown_skips():
    messages = []
    dispatcher = ActionDispatcher(RecordingOutput(), {"blink": "enter"}, 1.0, log=messages.append)
    dispatcher.dispatch(TriggerEvent("blink", "blink", 0.0))
    dispatcher.dispatch(TriggerEvent("blink", "blink", 0.5))
    assert len(messages) == 1 and "cooldown" in messages[0]


def test_blink_cooldown_blocks_rapid_repeat():
    trigger = BlinkTrigger(BlinkConfig(min_duration_s=0.15, cooldown_s=1.0))
    # Two deliberate blinks close together — only the first should fire.
    events = run(trigger, [(0.5, False), (0.3, True), (0.5, False), (0.3, True), (0.5, False)])
    assert len(events) == 1


def test_blink_cooldown_allows_after_expiry():
    trigger = BlinkTrigger(BlinkConfig(min_duration_s=0.15, cooldown_s=1.0))
    events = run(trigger, [(0.5, False), (0.3, True), (1.5, False), (0.3, True), (0.5, False)])
    assert len(events) == 2


def test_blink_with_head_turned_is_ignored():
    messages = []
    trigger = BlinkTrigger(BlinkConfig(min_duration_s=0.15), log=messages.append)
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
    assert len(events) == 1 and events[0].action == "head_shake"


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


def nod(trigger, pitches, start=0.0):
    events = []
    for i, pitch in enumerate(pitches):
        event = trigger.update(Observation(start + i / FPS, face_present=True, head_pitch=pitch))
        if event:
            events.append(event)
    return events


def test_nod_down_fires_on_return():
    trigger = NodTrigger(NodConfig())
    pitches = [0.0] * 5 + sweep(0, 20, 5) + sweep(20, 0, 5) + [0.0] * 5
    events = nod(trigger, pitches)
    assert len(events) == 1 and events[0].action == "nod_down"


def test_nod_up_fires_on_return():
    trigger = NodTrigger(NodConfig())
    pitches = [0.0] * 5 + sweep(0, -20, 5) + sweep(-20, 0, 5) + [0.0] * 5
    events = nod(trigger, pitches)
    assert len(events) == 1 and events[0].action == "nod_up"


def test_slow_tilt_does_not_fire():
    trigger = NodTrigger(NodConfig(amplitude_deg=12.0, max_duration_s=0.8))
    # Hold past threshold for 1.5 s then return — too slow
    pitches = [0.0] * 5 + [20.0] * 45 + [0.0] * 5
    assert nod(trigger, pitches) == []


def test_nod_cooldown_blocks_rapid_repeat():
    trigger = NodTrigger(NodConfig(cooldown_s=1.0))
    one = sweep(0, 20, 5) + sweep(20, 0, 5)
    assert len(nod(trigger, [0.0] * 5 + one + [0.0] * 3 + one)) == 1


def test_head_tracker_is_relative_to_usual_pose():
    tracker = HeadTracker(HeadConfig())
    for i in range(60):
        tracker.update(Signals(i / FPS, face_present=True, head_yaw_deg=10.0))
    yaw, pitch = tracker.update(Signals(2.0, face_present=True, head_yaw_deg=35.0))
    assert yaw == 25.0
    assert pitch is None


class FakeSource:
    def __init__(self, provides):
        self.name = "fake"
        self.provides = frozenset(provides)


def test_triggers_needing_missing_signals_are_skipped_with_a_notice():
    messages = []
    triggers = supported_triggers(create_triggers(Config()), FakeSource({EYE_OPENNESS}), messages.append)
    assert [t.name for t in triggers] == ["blink"]
    assert "head_shake: disabled (source fake has no head_pose)" in messages


def test_all_triggers_kept_when_source_provides_everything():
    messages = []
    all_triggers = create_triggers(Config())
    kept = supported_triggers(all_triggers, FakeSource({EYE_OPENNESS, HEAD_POSE}), messages.append)
    assert kept == all_triggers
    assert messages == []


def test_blink_works_without_head_pose():
    trigger = BlinkTrigger(BlinkConfig(min_duration_s=0.15))
    assert trigger.needs == {EYE_OPENNESS}
    assert len(run(trigger, [(1.0, False), (0.3, True), (0.5, False)])) == 1
