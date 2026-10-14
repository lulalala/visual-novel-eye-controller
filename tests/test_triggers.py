from dataclasses import replace

import pytest

from vn_eye.config import Config, HeadConfig, apply_overrides
from vn_eye.eyes import Observation
from vn_eye.head import HeadTracker
from vn_eye.outputs import ActionDispatcher
from vn_eye.sources import EYE_OPENNESS, HEAD_POSE, Signals
from vn_eye.triggers import GestureTrigger, TriggerEvent, create_triggers, supported_triggers

FPS = 30
DEFAULTS = Config().gestures


def gesture(name, log=None, **changes):
    return GestureTrigger(name, replace(DEFAULTS[name], **changes), log)


def obs(i, closed=False, yaw=0.0, pitch=0.0, face=True, ready=True):
    if not face:
        return Observation(i / FPS, face_present=False)
    return Observation(i / FPS, face_present=True, ready=ready, closed=closed,
                       head_yaw=yaw, head_pitch=pitch)


def drive(triggers, observations):
    """Feeds every trigger in order each frame. Returns the fired events."""
    events = []
    for o in observations:
        for trigger in triggers:
            event = trigger.update(o)
            if event:
                events.append(event)
    return events


def eyes(segments, start=0):
    """segments: list of (frames, closed)."""
    result, i = [], start
    for frames, closed in segments:
        for _ in range(frames):
            result.append(obs(i, closed=closed))
            i += 1
    return result


def head(values, axis, start=0):
    return [obs(start + i, **{axis: v}) for i, v in enumerate(values)]


def sweep(a, b, frames):
    return [a + (b - a) * i / frames for i in range(frames)]


# Blink


def test_normal_blink_does_not_fire():
    trigger = gesture("blink", hold_min_s=0.45)
    assert drive([trigger], eyes([(30, False), (6, True), (30, False)])) == []


def test_blink_fires_on_the_reopen_frame():
    trigger = gesture("blink", hold_min_s=0.45)
    events = drive([trigger], eyes([(30, False), (18, True), (15, False)]))
    assert len(events) == 1
    assert events[0].action == "blink"
    assert events[0].timestamp == 48 / FPS


def test_too_long_closure_is_canceled():
    trigger = gesture("blink", hold_min_s=0.45, hold_max_s=2.0)
    assert drive([trigger], eyes([(30, False), (90, True), (30, False)])) == []


def test_losing_face_cancels_closure():
    messages = []
    trigger = gesture("blink", messages.append, hold_min_s=0.45)
    stream = eyes([(30, False), (9, True)]) + [obs(39, face=False)] + eyes([(9, True), (15, False)], start=40)
    assert drive([trigger], stream) == []
    assert "face lost" in messages[0]


def test_not_ready_ignores_closure():
    trigger = gesture("blink")
    stream = [obs(i, closed=i >= 10, ready=False) for i in range(60)]
    assert drive([trigger], stream) == []


def test_short_and_too_long_closures_are_logged():
    messages = []
    trigger = gesture("blink", messages.append, hold_min_s=0.45)
    drive([trigger], eyes([(30, False), (6, True), (15, False), (90, True), (15, False)]))
    assert len(messages) == 2
    assert messages[0] == "blink: eyes_closed 0.20s (too short, min 0.45s)"
    assert "too long" in messages[1]


def test_successful_blink_is_not_logged_by_trigger():
    messages = []
    trigger = gesture("blink", messages.append, hold_min_s=0.45)
    assert len(drive([trigger], eyes([(30, False), (18, True), (15, False)]))) == 1
    assert messages == []


def test_blink_cooldown_blocks_rapid_repeat():
    messages = []
    trigger = gesture("blink", messages.append, hold_min_s=0.15, cooldown_s=1.0)
    events = drive([trigger], eyes([(15, False), (9, True), (15, False), (9, True), (15, False)]))
    assert len(events) == 1
    assert "cooldown" in messages[0]


def test_zero_blink_cooldown_allows_rapid_repeat():
    trigger = gesture("blink", hold_min_s=0.15, cooldown_s=0.0)
    events = drive([trigger], eyes([(15, False), (9, True), (6, False), (9, True), (15, False)]))
    assert len(events) == 2


def test_blink_cooldown_allows_after_expiry():
    trigger = gesture("blink", hold_min_s=0.15, cooldown_s=1.0)
    events = drive([trigger], eyes([(15, False), (9, True), (45, False), (9, True), (15, False)]))
    assert len(events) == 2


def test_blink_fires_with_head_turned():
    # The head-turn filter was removed; blinks count whatever the head does.
    trigger = gesture("blink")
    stream = [obs(i, closed=8 <= i < 16, yaw=20.0) for i in range(30)]
    assert len(drive([trigger], stream)) == 1


# Head shake


def test_head_shake_left_right_fires():
    trigger = gesture("head_shake")
    yaws = [0.0] * 10 + sweep(0, -25, 6) + sweep(-25, 25, 10) + sweep(25, 0, 6) + [0.0] * 10
    events = drive([trigger], head(yaws, "yaw"))
    assert len(events) == 1 and events[0].action == "head_shake"


def test_head_shake_right_left_fires_too():
    trigger = gesture("head_shake")
    yaws = [0.0] * 10 + sweep(0, 25, 6) + sweep(25, -25, 10) + sweep(-25, 0, 6) + [0.0] * 5
    assert len(drive([trigger], head(yaws, "yaw"))) == 1


def test_head_shake_fires_on_return_from_second_side():
    trigger = gesture("head_shake")
    yaws = [0.0] * 10 + sweep(0, -25, 6) + sweep(-25, 25, 10) + [25.0] * 10
    # Still turned to the second side: the second pose hasn't ended yet.
    assert drive([trigger], head(yaws, "yaw")) == []
    events = drive([trigger], head([5.0] * 3, "yaw", start=len(yaws)))
    assert len(events) == 1


def test_head_shake_order_only_without_any_order():
    trigger = gesture("head_shake", any_order=False)  # steps: head_left, then head_right
    right_first = [0.0] * 10 + sweep(0, -25, 6) + sweep(-25, 25, 10) + sweep(25, 0, 6) + [0.0] * 5
    assert drive([trigger], head(right_first, "yaw")) == []


def test_single_turn_does_not_fire():
    trigger = gesture("head_shake")
    yaws = [0.0] * 10 + sweep(0, -30, 6) + [-30.0] * 30 + sweep(-30, 0, 6) + [0.0] * 10
    assert drive([trigger], head(yaws, "yaw")) == []


def test_slow_look_left_then_right_does_not_fire():
    messages = []
    trigger = gesture("head_shake", messages.append)
    # Look left for 1.5 s, then swing right and back: the whole gesture took too long.
    yaws = [0.0] * 10 + [25.0] * 45 + sweep(25, -25, 6) + sweep(-25, 0, 6) + [0.0] * 5
    assert drive([trigger], head(yaws, "yaw")) == []
    assert "too slow" in messages[0]


def test_head_shake_cooldown_blocks_continued_shaking():
    trigger = gesture("head_shake", cooldown_s=1.5)
    one = sweep(0, -25, 4) + sweep(-25, 25, 6) + sweep(25, 0, 4)
    assert len(drive([trigger], head([0.0] * 5 + one + one + [0.0] * 5, "yaw"))) == 1


def test_head_left_is_positive_yaw():
    trigger = GestureTrigger("look", replace(DEFAULTS["nod_down"], steps=["head_left"]))
    assert len(drive([trigger], head([0.0] * 5 + [20.0] * 5 + [0.0] * 5, "yaw"))) == 1


# Nod


def test_nod_down_fires_on_return():
    trigger = gesture("nod_down")
    pitches = [0.0] * 5 + sweep(0, 20, 5) + sweep(20, 0, 5) + [0.0] * 5
    assert [e.action for e in drive([trigger], head(pitches, "pitch"))] == ["nod_down"]


def test_nod_up_fires_on_return():
    trigger = gesture("nod_up")
    pitches = [0.0] * 5 + sweep(0, -20, 5) + sweep(-20, 0, 5) + [0.0] * 5
    assert [e.action for e in drive([trigger], head(pitches, "pitch"))] == ["nod_up"]


def test_slow_tilt_does_not_fire():
    messages = []
    trigger = gesture("nod_down", messages.append)
    pitches = [0.0] * 5 + [20.0] * 45 + [0.0] * 5
    assert drive([trigger], head(pitches, "pitch")) == []
    assert "too long" in messages[0]


def test_wobble_at_the_threshold_does_not_fire():
    trigger = gesture("nod_down")  # past 12°, release below 8°
    pitches = [0.0] * 5 + sweep(0, 12.5, 30) + [12.5, 11.5, 12.5, 11.0, 12.5] * 6 + [12.0] * 5
    assert drive([trigger], head(pitches, "pitch")) == []


def test_nod_cooldown_blocks_rapid_repeat():
    trigger = gesture("nod_down", cooldown_s=1.0)
    one = sweep(0, 20, 5) + sweep(20, 0, 5)
    assert len(drive([trigger], head([0.0] * 5 + one + [0.0] * 3 + one + [0.0] * 3, "pitch"))) == 1


def test_losing_head_pose_cancels_nod():
    trigger = gesture("nod_down")
    stream = head([0.0] * 5 + [20.0] * 5, "pitch") + [obs(10, face=False)] + head([0.0] * 5, "pitch", start=11)
    assert drive([trigger], stream) == []


# Gestures made of gestures


def combo_config(**changes):
    return {
        "gestures": {
            "nod_down": {"enabled": True, "output": ""},
            "blink_nod": {"steps": ["blink", "nod_down"], "within_s": 2.0, "output": "space", **changes},
        }
    }


def blink_then_nod(gap_frames=5):
    stream = [obs(i, closed=10 <= i < 16) for i in range(20)]
    start = 20 + gap_frames
    stream += [obs(20 + i) for i in range(gap_frames)]
    stream += [obs(start + i, pitch=p) for i, p in enumerate(sweep(0, 20, 5) + sweep(20, 0, 5) + [0.0] * 5)]
    return stream


def test_gesture_of_gestures_fires_and_its_steps_fire_too():
    triggers = create_triggers(apply_overrides(Config(), combo_config()))
    events = drive(triggers, blink_then_nod())
    assert [e.action for e in events] == ["blink", "nod_down", "blink_nod"]
    assert events[1].timestamp == events[2].timestamp


def test_gesture_steps_in_the_wrong_order_do_not_fire():
    triggers = create_triggers(apply_overrides(Config(), combo_config()))
    nod_first = [obs(i, pitch=p) for i, p in enumerate(sweep(0, 20, 5) + sweep(20, 0, 5) + [0.0] * 5)]
    nod_first += [obs(15 + i, closed=5 <= i < 11) for i in range(20)]
    assert "blink_nod" not in [e.action for e in drive(triggers, nod_first)]


def test_gesture_of_gestures_too_slow_does_not_fire():
    messages = []
    triggers = create_triggers(apply_overrides(Config(), combo_config(within_s=1.0)), messages.append)
    events = drive(triggers, blink_then_nod(gap_frames=30))
    assert "blink_nod" not in [e.action for e in events]
    assert any("blink_nod" in m and "too slow" in m for m in messages)


def test_gestures_are_built_after_their_steps():
    config = apply_overrides(Config(), {"gestures": {
        "aaa": {"steps": ["blink", "blink"], "output": "space"},
    }})
    names = [t.name for t in create_triggers(config)]
    assert names.index("blink") < names.index("aaa")


@pytest.mark.parametrize("gestures, message", [
    ({"x": {"steps": ["wink"]}}, "unknown step 'wink'"),
    ({"x": {"steps": []}}, "gestures.x.steps must list"),
    ({"x": {"steps": ["y"]}, "y": {"steps": ["x"]}}, "loop"),
    ({"x": {"steps": ["nod_down"]}}, "nod_down is disabled"),
    ({"x": {"steps": ["head_up"], "past_deg": 10.0, "release_deg": 10.0}}, "gestures.x.release_deg"),
    ({"x": {"steps": ["eyes_closed"], "hold_min_s": 1.0, "hold_max_s": 0.5}}, "gestures.x.hold_max_s"),
    ({"x": {"steps": ["eyes_closed"], "cooldown_s": -1.0}}, "gestures.x.cooldown_s"),
])
def test_invalid_gestures_are_rejected(gestures, message):
    with pytest.raises(ValueError, match=message):
        create_triggers(apply_overrides(Config(), {"gestures": gestures}))


# Dispatching and sources


class RecordingOutput:
    def __init__(self):
        self.sent = []

    def send(self, name):
        self.sent.append(name)


def test_dispatcher_maps_actions_without_its_own_cooldown():
    out = RecordingOutput()
    dispatcher = ActionDispatcher(out, {"blink": "enter", "nod_down": "down"})
    assert dispatcher.dispatch(TriggerEvent("blink", "blink", 0.0))
    assert dispatcher.dispatch(TriggerEvent("nod_down", "nod_down", 0.1))
    assert not dispatcher.dispatch(TriggerEvent("nod_up", "nod_up", 0.2))
    assert out.sent == ["enter", "down"]


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


def test_gesture_of_gestures_needs_what_its_steps_need():
    triggers = create_triggers(apply_overrides(Config(), combo_config()))
    combo = next(t for t in triggers if t.name == "blink_nod")
    assert combo.needs == {EYE_OPENNESS, HEAD_POSE}


def test_all_triggers_kept_when_source_provides_everything():
    messages = []
    all_triggers = create_triggers(Config())
    kept = supported_triggers(all_triggers, FakeSource({EYE_OPENNESS, HEAD_POSE}), messages.append)
    assert kept == all_triggers
    assert messages == []


def test_blink_works_without_head_pose():
    trigger = gesture("blink")
    assert trigger.needs == {EYE_OPENNESS}
    stream = [Observation(i / FPS, face_present=True, ready=True, closed=10 <= i < 19) for i in range(30)]
    assert len(drive([trigger], stream)) == 1
