from dataclasses import replace

import pytest

from vn_eye.config import Config, GestureConfig, HeadConfig, StepConfig, apply_overrides
from vn_eye.eyes import Observation
from vn_eye.head import HeadTracker
from vn_eye.outputs import ActionDispatcher
from vn_eye.sources import EYE_OPENNESS, HEAD_POSE, Signals
from vn_eye.triggers import GestureTrigger, TriggerEvent, create_triggers, replay, supported_triggers

FPS = 30
DEFAULTS = Config().gestures


def gesture(name, log=None, steps=None, **changes):
    """A built-in gesture, with changes to the gesture and to steps by index."""
    cfg = DEFAULTS[name]
    if steps:
        cfg = replace(cfg, steps=[replace(s, **steps.get(i, {})) for i, s in enumerate(cfg.steps)])
    return GestureTrigger(name, replace(cfg, **changes), log)


def custom(*steps, log=None, **changes):
    return GestureTrigger("custom", GestureConfig(steps=list(steps), **changes), log)


def obs(i, eyes=1.0, yaw=0.0, pitch=0.0, face=True, ready=True):
    if not face:
        return Observation(i / FPS, face_present=False)
    return Observation(i / FPS, face_present=True, ready=ready, combined=eyes, baseline=1.0,
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
            result.append(obs(i, eyes=0.3 if closed else 1.0))
            i += 1
    return result


def head(values, axis, start=0):
    return [obs(start + i, **{axis: v}) for i, v in enumerate(values)]


def sweep(a, b, frames):
    return [a + (b - a) * i / frames for i in range(frames)]


# Blink


def test_normal_blink_does_not_fire():
    trigger = gesture("blink", steps={1: {"after_min_s": 0.45}})
    assert drive([trigger], eyes([(30, False), (6, True), (30, False)])) == []


def test_blink_fires_on_the_reopen_frame():
    trigger = gesture("blink", steps={1: {"after_min_s": 0.45}})
    events = drive([trigger], eyes([(30, False), (18, True), (15, False)]))
    assert len(events) == 1
    assert events[0].action == "blink"
    assert events[0].timestamp == 48 / FPS


def test_too_long_closure_is_canceled_while_still_closed():
    messages = []
    trigger = gesture("blink", messages.append)
    assert drive([trigger], eyes([(30, False), (90, True), (30, False)])) == []
    assert messages == ["blink: step 2 not reached in time (too long, max 2.00s)"]


def test_losing_face_cancels_closure():
    messages = []
    trigger = gesture("blink", messages.append)
    stream = eyes([(30, False), (9, True)]) + [obs(39, face=False)] + eyes([(9, True), (15, False)], start=40)
    assert drive([trigger], stream) == []
    assert "face lost" in messages[0]


def test_not_ready_ignores_closure():
    trigger = gesture("blink")
    stream = [obs(i, eyes=0.3 if i >= 10 else 1.0, ready=False) for i in range(60)]
    assert drive([trigger], stream) == []


def test_too_short_closure_is_logged():
    messages = []
    trigger = gesture("blink", messages.append, steps={1: {"after_min_s": 0.45}})
    drive([trigger], eyes([(30, False), (6, True), (15, False)]))
    assert messages == ["blink: step 2 came 0.20s after step 1 (too short, min 0.45s)"]


def test_successful_blink_is_not_logged_by_trigger():
    messages = []
    trigger = gesture("blink", messages.append)
    assert len(drive([trigger], eyes([(30, False), (18, True), (15, False)]))) == 1
    assert messages == []


def test_blink_cooldown_blocks_rapid_repeat():
    messages = []
    trigger = gesture("blink", messages.append, cooldown_s=1.0)
    events = drive([trigger], eyes([(15, False), (9, True), (15, False), (9, True), (15, False)]))
    assert len(events) == 1
    assert "cooldown" in messages[0]


def test_zero_blink_cooldown_allows_rapid_repeat():
    trigger = gesture("blink", cooldown_s=0.0)
    events = drive([trigger], eyes([(15, False), (9, True), (6, False), (9, True), (15, False)]))
    assert len(events) == 2


def test_blink_cooldown_allows_after_expiry():
    trigger = gesture("blink", cooldown_s=1.0)
    events = drive([trigger], eyes([(15, False), (9, True), (45, False), (9, True), (15, False)]))
    assert len(events) == 2


def blink_with_head(**head_values):
    return [obs(i, eyes=0.3 if 8 <= i < 16 else 1.0, **head_values) for i in range(30)]


def test_blink_fires_with_head_near_center():
    trigger = gesture("blink")
    assert len(drive([trigger], blink_with_head(yaw=15.0, pitch=-10.0))) == 1


@pytest.mark.parametrize("head_values", [{"yaw": 25.0}, {"yaw": -25.0}, {"pitch": 20.0}, {"pitch": -20.0}])
def test_blink_is_ignored_with_head_turned_away(head_values):
    trigger = gesture("blink")
    assert drive([trigger], blink_with_head(**head_values)) == []


def test_turning_away_mid_closure_cancels_and_logs():
    messages = []
    trigger = gesture("blink", messages.append)
    stream = [obs(i, eyes=0.3 if 8 <= i < 16 else 1.0, yaw=25.0 if i >= 12 else 0.0) for i in range(30)]
    assert drive([trigger], stream) == []
    assert messages == ["blink: canceled (head yaw +25° outside its limit)"]


def test_closure_that_began_while_turned_does_not_count_after_returning():
    trigger = gesture("blink")
    stream = [obs(i, eyes=0.3 if 8 <= i < 20 else 1.0, yaw=25.0 if i < 12 else 0.0) for i in range(40)]
    assert drive([trigger], stream) == []


def test_guards_can_be_removed():
    trigger = gesture("blink", guards=[])
    assert len(drive([trigger], blink_with_head(yaw=40.0))) == 1


def test_guard_without_head_pose_does_not_block():
    trigger = gesture("blink")
    stream = [Observation(i / FPS, face_present=True, ready=True, baseline=1.0,
                          combined=0.3 if 8 <= i < 16 else 1.0) for i in range(30)]
    assert len(drive([trigger], stream)) == 1


@pytest.mark.parametrize("guard, message", [
    (StepConfig(signal="eyes", below_ratio=0.5), "guards[0].signal"),
    (StepConfig(signal="yaw"), "guards[0] needs"),
    (StepConfig(signal="yaw", above_deg=5.0, below_deg=-5.0), "guards[0].above_deg"),
    (StepConfig(signal="yaw", below_deg=5.0, hold_s=1.0), "guards[0]: a guard has no timing"),
])
def test_invalid_guard_is_rejected(guard, message):
    with pytest.raises(ValueError, match=message.replace("[", r"\[").replace("]", r"\]")):
        gesture("blink", guards=[guard])


def test_eyes_already_closed_at_start_do_not_count():
    trigger = gesture("blink")
    assert drive([trigger], eyes([(9, True), (15, False)])) == []


def test_eye_box_is_relative_to_the_baseline():
    trigger = gesture("blink")
    stream = [Observation(i / FPS, face_present=True, ready=True, baseline=0.3,
                          combined=0.1 if 10 <= i < 19 else 0.3) for i in range(30)]
    assert len(drive([trigger], stream)) == 1


# Per-step limits and hold


def test_double_blink_with_short_closures_and_a_longer_pause_fires():
    closed, opened = StepConfig(signal="eyes", below_ratio=0.55), StepConfig(signal="eyes", above_ratio=0.75)
    trigger = custom(
        closed,
        replace(opened, after_max_s=0.3),
        replace(closed, after_max_s=0.8),
        replace(opened, after_max_s=0.3),
    )
    stream = eyes([(10, False), (5, True), (18, False), (5, True), (10, False)])
    assert len(drive([trigger], stream)) == 1
    # The same pause with a slow first closure: step 2 comes too late.
    assert drive([custom(*trigger.config.steps)], eyes([(10, False), (15, True), (18, False), (5, True), (10, False)])) == []


def test_hold_fires_while_still_inside_the_box():
    trigger = custom(StepConfig(signal="eyes", below_ratio=0.55, hold_s=1.0))
    events = drive([trigger], eyes([(10, False), (60, True)]))
    assert len(events) == 1
    assert events[0].timestamp == 40 / FPS


def test_leaving_the_box_before_hold_does_not_count():
    trigger = custom(StepConfig(signal="eyes", below_ratio=0.55, hold_s=1.0))
    assert drive([trigger], eyes([(10, False), (20, True), (10, False), (20, True), (10, False)])) == []


def test_steps_can_use_different_signals():
    trigger = custom(StepConfig(signal="pitch", above_deg=12.0),
                     StepConfig(signal="eyes", below_ratio=0.55, after_max_s=1.0))
    stream = [obs(i, pitch=20.0 if i >= 5 else 0.0, eyes=0.3 if i >= 15 else 1.0) for i in range(20)]
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


def test_head_shake_fires_on_reaching_the_second_side():
    trigger = gesture("head_shake")
    yaws = [0.0] * 10 + [-20.0] * 5 + [0.0] * 3 + [20.0] * 10
    events = drive([trigger], head(yaws, "yaw"))
    assert len(events) == 1
    assert events[0].timestamp == 18 / FPS


def test_head_shake_order_only_without_any_order():
    trigger = gesture("head_shake", any_order=False)  # steps: yaw above 15 (left), then below -15
    right_first = [0.0] * 10 + sweep(0, -25, 6) + sweep(-25, 25, 10) + sweep(25, 0, 6) + [0.0] * 5
    assert drive([trigger], head(right_first, "yaw")) == []


def test_single_turn_does_not_fire():
    trigger = gesture("head_shake")
    yaws = [0.0] * 10 + sweep(0, -30, 6) + [-30.0] * 30 + sweep(-30, 0, 6) + [0.0] * 10
    assert drive([trigger], head(yaws, "yaw")) == []


def test_slow_look_left_then_right_does_not_fire():
    messages = []
    trigger = gesture("head_shake", messages.append)
    yaws = [0.0] * 10 + [25.0] * 45 + sweep(25, -25, 6) + sweep(-25, 0, 6) + [0.0] * 5
    assert drive([trigger], head(yaws, "yaw")) == []
    assert "too slow" in messages[0]


def test_head_shake_cooldown_blocks_continued_shaking():
    trigger = gesture("head_shake", cooldown_s=1.5)
    one = sweep(0, -25, 4) + sweep(-25, 25, 6) + sweep(25, 0, 4)
    assert len(drive([trigger], head([0.0] * 5 + one + one + [0.0] * 5, "yaw"))) == 1


def test_positive_yaw_is_your_left():
    # Documents the sign; a live check confirms it against a real camera.
    trigger = custom(StepConfig(signal="yaw", above_deg=15.0))
    assert len(drive([trigger], head([0.0] * 5 + [20.0] * 5, "yaw"))) == 1


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


def test_swinging_from_down_straight_to_up_passes_center():
    trigger = gesture("nod_down")
    pitches = [0.0] * 5 + [20.0] * 5 + sweep(20, -20, 6) + [-20.0] * 5
    assert [e.action for e in drive([trigger], head(pitches, "pitch"))] == ["nod_down"]


def test_wobble_at_the_threshold_does_not_fire():
    trigger = gesture("nod_down")  # in past 12°, back to center within 8°
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
            "blink_nod": {
                "steps": [{"gesture": "blink"}, {"gesture": "nod_down", "after_max_s": 1.5}],
                "output": "space", **changes,
            },
        }
    }


def blink_then_nod(gap_frames=5):
    stream = [obs(i, eyes=0.3 if 10 <= i < 16 else 1.0) for i in range(20)]
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
    nod_first += [obs(15 + i, eyes=0.3 if 5 <= i < 11 else 1.0) for i in range(20)]
    assert "blink_nod" not in [e.action for e in drive(triggers, nod_first)]


def test_gesture_of_gestures_too_slow_does_not_fire():
    messages = []
    triggers = create_triggers(apply_overrides(Config(), combo_config()), messages.append)
    events = drive(triggers, blink_then_nod(gap_frames=60))
    assert "blink_nod" not in [e.action for e in events]
    assert any(m.startswith("blink_nod: step 2 not reached in time") for m in messages)


def test_gestures_are_built_after_their_steps():
    config = apply_overrides(Config(), {"gestures": {
        "aaa": {"steps": [{"gesture": "blink"}, {"gesture": "blink"}], "output": "space"},
    }})
    names = [t.name for t in create_triggers(config)]
    assert names.index("blink") < names.index("aaa")


@pytest.mark.parametrize("gestures, message", [
    ({"x": {"steps": [{"gesture": "wink"}]}}, "unknown gesture 'wink'"),
    ({"x": {"steps": []}}, "gestures.x.steps must list"),
    ({"x": {"steps": [{"gesture": "y"}]}, "y": {"steps": [{"gesture": "x"}]}}, "loop"),
    ({"x": {"steps": [{"gesture": "nod_down"}]}}, "nod_down is disabled"),
    ({"x": {"steps": [{"signal": "eyes", "gesture": "blink"}]}}, "not both"),
    ({"x": {"steps": [{"above_deg": 1.0}]}}, "not neither"),
    ({"x": {"steps": [{"signal": "roll", "above_deg": 1.0}]}}, r"steps\[0\].signal must be one of"),
    ({"x": {"steps": [{"signal": "eyes", "above_deg": 1.0}]}}, "eyes uses above_ratio/below_ratio"),
    ({"x": {"steps": [{"signal": "pitch"}]}}, "needs above_deg, below_deg or both"),
    ({"x": {"steps": [{"signal": "pitch", "above_deg": 8.0, "below_deg": -8.0}]}}, r"steps\[0\].above_deg must be below"),
    ({"x": {"steps": [{"signal": "yaw", "above_deg": 1.0, "after_min_s": 1.0, "after_max_s": 0.5}]}}, r"steps\[0\].after_max_s"),
    ({"x": {"steps": [{"signal": "yaw", "above_deg": 1.0}], "cooldown_s": -1.0}}, "gestures.x.cooldown_s"),
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
    stream = [Observation(i / FPS, face_present=True, ready=True, baseline=1.0,
                          combined=0.3 if 10 <= i < 19 else 1.0) for i in range(30)]
    assert len(drive([trigger], stream)) == 1


# Replaying recordings (for the settings window)


def test_replay_reports_when_it_fires_and_the_step_times():
    result = replay(Config(), "blink", eyes([(30, False), (9, True), (15, False)]))
    assert result.fired_at == 39 / FPS
    assert result.reason == "fires at 1.30s"
    assert [i for i, _ in result.steps] == [0, 1]


def test_replay_reports_why_it_did_not_fire():
    result = replay(Config(), "nod_down", head([0.0] * 5 + [20.0] * 45 + [0.0] * 5, "pitch"))
    assert result.fired_at is None
    assert result.reason == "step 2 not reached in time (too long, max 0.80s)"
    assert [i for i, _ in result.steps] == [0]


def test_replay_works_for_disabled_gestures_and_unreached_steps():
    assert replay(Config(), "nod_down", head([0.0] * 30, "pitch")).reason == "step 1 never reached"


def test_replay_reports_a_gesture_still_waiting_at_the_end():
    result = replay(Config(), "blink", eyes([(30, False), (20, True)]))
    assert result.reason.startswith("waiting for the next step")
    assert [i for i, _ in result.steps] == [0]


def test_replay_reports_an_attempt_that_expired_quietly():
    # A turn right with no turn left after it: the shake started but never finished.
    result = replay(Config(), "head_shake", head([0.0] * 5 + [-20.0] * 5 + [0.0] * 80, "yaw"))
    assert result.reason == "didn't finish in time (too slow, max 1.00s)"
    assert [i for i, _ in result.steps] == [1]
