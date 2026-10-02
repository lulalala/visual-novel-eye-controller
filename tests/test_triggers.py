from vn_eye.config import LongBlinkConfig
from vn_eye.eyes import EyeObservation
from vn_eye.outputs import ActionDispatcher
from vn_eye.triggers import LongBlinkTrigger, TriggerEvent

FPS = 30


def run(trigger, segments, start=0.0):
    """segments: list of (duration_s, closed). Returns fired events."""
    events = []
    t = start
    for duration, closed in segments:
        end = t + duration
        while t < end - 1e-9:
            event = trigger.update(EyeObservation(t, face_present=True, ready=True, closed=closed))
            if event:
                events.append(event)
            t += 1 / FPS
    return events


def test_normal_blink_does_not_fire():
    trigger = LongBlinkTrigger(LongBlinkConfig())
    assert run(trigger, [(1.0, False), (0.2, True), (1.0, False)]) == []


def test_long_blink_fires_on_reopen():
    trigger = LongBlinkTrigger(LongBlinkConfig())
    events = run(trigger, [(1.0, False), (0.6, True), (0.5, False)])
    assert len(events) == 1
    assert events[0].action == "next"
    assert 1.6 <= events[0].timestamp < 1.7


def test_too_long_closure_is_cancelled():
    trigger = LongBlinkTrigger(LongBlinkConfig(max_duration_s=2.0))
    assert run(trigger, [(1.0, False), (3.0, True), (1.0, False)]) == []


def test_hold_mode_fires_once_while_closed():
    trigger = LongBlinkTrigger(LongBlinkConfig(fire_on="hold"))
    events = run(trigger, [(1.0, False), (3.0, True), (1.0, False)])
    assert len(events) == 1
    assert 1.45 <= events[0].timestamp < 1.5


def test_losing_face_cancels_closure():
    trigger = LongBlinkTrigger(LongBlinkConfig())
    run(trigger, [(1.0, False), (0.3, True)])
    trigger.update(EyeObservation(1.31, face_present=False))
    events = run(trigger, [(0.3, True), (0.5, False)], start=1.35)
    assert events == []


def test_not_ready_ignores_closure():
    trigger = LongBlinkTrigger(LongBlinkConfig())
    for i in range(30):
        assert trigger.update(EyeObservation(i / FPS, face_present=True, ready=False, closed=True)) is None


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
