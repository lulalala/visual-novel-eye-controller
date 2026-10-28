from dataclasses import replace

import pytest

from eyeokuri.config import Config, apply_overrides
from eyeokuri.engine import Engine
from eyeokuri.gui.model import log_tag
from eyeokuri.outputs import APP_OUTPUTS, MOUSE_OUTPUTS
from eyeokuri.sources import EYE_OPENNESS, HEAD_POSE, Signals

FPS = 30


class ScriptedSource:
    """Plays back (eye openness, yaw) pairs, one per read()."""

    name = "scripted"
    provides = frozenset({EYE_OPENNESS, HEAD_POSE})

    def __init__(self, samples):
        self._samples = list(samples)
        self._i = 0

    def read(self):
        eyes, yaw = self._samples[self._i]
        t = self._i / FPS
        self._i += 1
        if eyes is None:
            return Signals(t, face_present=False)
        return Signals(t, face_present=True, eye_openness=(eyes, eyes), head_yaw_deg=yaw, head_pitch_deg=0.0)

    def debug_view(self):
        return None

    def close(self):
        pass


class RecordingOutput:
    def __init__(self):
        self.sent = []
        self.held = []

    def send(self, name):
        self.sent.append(name)

    def down(self, name):
        self.held.append(("down", name))

    def up(self, name):
        self.held.append(("up", name))


def calibrate(frames=90):
    return [(0.3, 0.0)] * frames


def blink():
    return [(0.05, 0.0)] * 8 + [(0.3, 0.0)] * 30


def shake():
    return [(0.3, y) for y in [0, 10, 20, 25, 20, 0, -20, -25, -20, 0]] + [(0.3, 0.0)] * 30


def make(samples, config=None):
    messages, sounds, output = [], [], RecordingOutput()
    engine = Engine(config or Config(), messages.append, ScriptedSource(samples), output, sounds.append)
    return engine, output, messages, sounds


def run(engine, frames):
    return [engine.step() for _ in range(frames)]


def test_blink_sends_its_output_and_beeps():
    samples = calibrate() + blink()
    engine, output, messages, sounds = make(samples)
    frames = run(engine, len(samples))
    assert output.sent == ["enter"]
    assert sum(f.fired for f in frames) == 1
    assert any(m.startswith("blink: ") and m.endswith("-> enter") for m in messages)
    assert sounds == ["trigger"]


def test_gesture_without_an_output_is_only_logged():
    config = apply_overrides(Config(), {"gestures": {"blink": {"output": ""}}})
    samples = calibrate() + blink()
    engine, output, messages, sounds = make(samples, config)
    frames = run(engine, len(samples))
    assert output.sent == []
    assert not any(f.fired for f in frames)
    assert any(m.startswith("blink: ") and "->" not in m for m in messages)
    assert sounds == []


def test_unknown_output_is_rejected_when_the_config_is_applied():
    config = apply_overrides(Config(), {"gestures": {"blink": {"output": "nonsense"}}})
    with pytest.raises(ValueError, match="gestures.blink.output"):
        make(calibrate(), config)


def test_unknown_output_message_lists_the_mouse_outputs():
    config = apply_overrides(Config(), {"gestures": {"blink": {"output": "nonsense"}}})
    with pytest.raises(ValueError) as e:
        make(calibrate(), config)
    assert all(name in str(e.value) for name in MOUSE_OUTPUTS)


def test_every_app_output_has_an_action():
    engine, *_ = make(calibrate())
    assert set(engine.app_actions) == APP_OUTPUTS


def test_head_shake_pauses_and_blinks_are_then_ignored():
    samples = calibrate() + shake() + blink()
    engine, output, messages, sounds = make(samples)
    run(engine, len(samples))
    assert engine.paused
    assert output.sent == []
    assert "Paused" in messages
    assert any(m.endswith("-> enter (paused, not sent)") for m in messages)


def test_new_config_takes_effect_on_the_next_step_and_keeps_calibration():
    samples = calibrate() + blink()
    engine, output, messages, sounds = make(samples)
    run(engine, 80)
    tracker = engine.eyes
    # Rebuilt gestures start fresh, so this applies before the blink starts.
    engine.set_config(apply_overrides(Config(), {"gestures": {"blink": {"output": "space"}}}))
    run(engine, len(samples) - 80)
    assert output.sent == ["space"]
    assert engine.eyes is tracker


def test_invalid_new_config_is_logged_and_the_old_one_stays_in_use():
    samples = calibrate() + blink()
    engine, output, messages, _ = make(samples)
    run(engine, 80)
    tracker, triggers = engine.eyes, engine.triggers
    bad = apply_overrides(Config(), {"gestures": {"blink": {"output": "nonsense"}},
                                     "eyes": {"warmup_s": 1.0}})
    engine.set_config(bad)
    run(engine, len(samples) - 80)
    assert any(m.startswith("Settings not applied: gestures.blink.output") for m in messages)
    assert engine.config == Config()
    assert engine.eyes is tracker and engine.triggers is triggers
    assert output.sent == ["enter"]


def _tags(messages):
    return {m: log_tag(m) for m in messages}


def test_log_window_colors_a_sent_output_as_fired():
    engine, _, messages, _ = make(calibrate() + blink())
    run(engine, len(calibrate() + blink()))
    sent = [m for m in messages if m.endswith("-> enter")]
    assert sent and all(log_tag(m) == "fire" for m in sent)


def test_log_window_colors_rejections_and_paused_outputs_as_rejected():
    quick = [(0.05, 0.0)] * 2 + [(0.3, 0.0)] * 30
    samples = calibrate() + quick + shake() + blink()
    engine, _, messages, _ = make(samples)
    run(engine, len(samples))
    tags = _tags(messages)
    assert [t for m, t in tags.items() if "too short" in m] == ["reject"]
    assert [t for m, t in tags.items() if m.endswith("(paused, not sent)")] == ["reject"]
    assert tags["Paused"] == ""
    assert all(t == "" for m, t in tags.items() if m.startswith("head_shake: "))


def test_log_window_leaves_settings_errors_plain_even_with_arrows():
    loop = {"a": {"steps": [{"gesture": "b"}]}, "b": {"steps": [{"gesture": "a"}]}}
    engine, _, messages, _ = make(calibrate(2))
    engine.set_config(apply_overrides(Config(), {"gestures": loop}))
    engine.step()
    errors = [m for m in messages if m.startswith("Settings not applied: ")]
    assert errors and " -> " in errors[0]
    assert log_tag(errors[0]) != "fire"


def test_changed_eye_settings_restart_calibration():
    engine, *_ = make(calibrate(10))
    tracker = engine.eyes
    engine.set_config(replace(Config(), eyes=replace(Config().eyes, warmup_s=1.0)))
    engine.step()
    assert engine.eyes is not tracker


def test_toggle_pause_from_another_thread_applies_on_the_next_step():
    engine, output, messages, sounds = make(calibrate(5))
    engine.toggle_pause()
    assert not engine.paused
    engine.step()
    assert engine.paused
    assert sounds == ["pause"]


def test_suspended_engine_sends_nothing_but_keeps_observing():
    samples = calibrate() + blink()
    engine, output, messages, sounds = make(samples)
    run(engine, 80)
    engine.set_suspended(True)
    frames = run(engine, len(samples) - 80)
    assert engine.suspended
    assert output.sent == []
    assert frames[-1].obs.face_present
    assert "Gestures off" in messages


def test_suspending_drops_a_half_done_gesture():
    samples = calibrate() + blink()
    engine, output, messages, sounds = make(samples)
    run(engine, 94)  # closed, not yet open again
    engine.set_suspended(True)
    engine.step()
    engine.set_suspended(False)
    run(engine, len(samples) - 95)
    assert output.sent == []
    assert "Gestures on" in messages


def test_head_shake_cannot_end_suspension_or_pause():
    samples = calibrate() + shake()
    engine, output, messages, sounds = make(samples)
    run(engine, 90)
    engine.set_suspended(True)
    run(engine, len(samples) - 90)
    assert engine.suspended
    assert not engine.paused


def test_engine_starts_paused_when_the_config_says_so():
    config = apply_overrides(Config(), {"app": {"paused": True}})
    samples = calibrate() + blink()
    engine, output, messages, sounds = make(samples, config)
    run(engine, len(samples))
    assert engine.paused
    assert output.sent == []
    assert any(m.startswith("Starting paused") for m in messages)


def test_new_config_keeps_the_live_paused_state():
    engine, *_ = make(calibrate(5))
    engine.toggle_pause()
    engine.step()
    engine.set_config(Config())
    engine.step()
    assert engine.paused


def hold_on_blink(output="ctrl", **gestures):
    return apply_overrides(Config(), {"gestures": {
        "blink": {"output": output, "output_mode": "toggle"}, **gestures,
    }})


def test_toggle_gesture_holds_its_output_until_it_fires_again():
    samples = calibrate() + blink() + blink()
    engine, output, messages, sounds = make(samples, hold_on_blink())
    frames = run(engine, len(calibrate() + blink()))
    assert output.held == [("down", "ctrl")]
    assert any(m.endswith("-> ctrl held") for m in messages)
    frames += run(engine, len(blink()))
    assert output.held == [("down", "ctrl"), ("up", "ctrl")]
    assert output.sent == []
    assert sum(f.fired for f in frames) == 2
    assert any(m.endswith("-> ctrl released") for m in messages)
    assert sounds == ["trigger", "trigger"]


def test_toggle_holds_a_mouse_button():
    samples = calibrate() + blink()
    engine, output, *_ = make(samples, hold_on_blink("mouse_left_click"))
    run(engine, len(samples))
    assert output.held == [("down", "mouse_left_click")]


def test_pausing_lets_go_of_a_held_output():
    samples = calibrate() + blink() + shake()
    engine, output, messages, _ = make(samples, hold_on_blink())
    run(engine, len(samples))
    assert engine.paused
    assert output.held == [("down", "ctrl"), ("up", "ctrl")]
    assert messages.index("Paused") < messages.index("Released ctrl: paused")


def test_toggle_gesture_while_paused_holds_nothing():
    config = apply_overrides(hold_on_blink(), {"app": {"paused": True}})
    samples = calibrate() + blink()
    engine, output, messages, _ = make(samples, config)
    run(engine, len(samples))
    assert output.held == []
    assert any(m.endswith("-> ctrl (paused, not sent)") for m in messages)


def test_losing_the_face_lets_go_of_a_held_output():
    samples = calibrate() + blink() + [(None, None)] * 3
    engine, output, messages, _ = make(samples, hold_on_blink())
    run(engine, len(samples))
    assert output.held == [("down", "ctrl"), ("up", "ctrl")]
    assert messages.count("Released ctrl: no face") == 1


def test_suspending_lets_go_of_a_held_output():
    samples = calibrate() + blink() + [(0.3, 0.0)]
    engine, output, messages, _ = make(samples, hold_on_blink())
    run(engine, len(samples) - 1)
    engine.set_suspended(True)
    engine.step()
    assert output.held == [("down", "ctrl"), ("up", "ctrl")]
    assert "Released ctrl: gestures off" in messages


def test_new_settings_let_go_of_a_held_output():
    samples = calibrate() + blink() + [(0.3, 0.0)]
    engine, output, messages, _ = make(samples, hold_on_blink())
    run(engine, len(samples) - 1)
    engine.set_config(hold_on_blink("shift"))
    engine.step()
    assert output.held == [("down", "ctrl"), ("up", "ctrl")]
    assert "Released ctrl: settings changed" in messages


def test_closing_lets_go_of_a_held_output():
    samples = calibrate() + blink()
    engine, output, messages, _ = make(samples, hold_on_blink())
    run(engine, len(samples))
    engine.close()
    engine.close()
    assert output.held == [("down", "ctrl"), ("up", "ctrl")]
    assert messages.count("Released ctrl: stopping") == 1


def test_log_window_colors_held_and_released_as_fired_and_a_release_plain():
    samples = calibrate() + blink() + blink() + blink() + shake()
    engine, _, messages, _ = make(samples, hold_on_blink())
    run(engine, len(samples))
    tags = _tags(messages)
    fired = [m for m in messages if m.endswith((" held", " released"))]
    assert len(fired) == 3 and all(tags[m] == "fire" for m in fired)
    assert tags["Released ctrl: paused"] == ""


@pytest.mark.parametrize("output", ["", "app_pause_toggle", "mouse_wheel_down"])
def test_toggle_needs_an_output_that_can_be_held(output):
    with pytest.raises(ValueError, match="gestures.blink.output_mode toggle needs a key"):
        make(calibrate(), hold_on_blink(output))


def test_unknown_output_mode_is_rejected():
    config = apply_overrides(Config(), {"gestures": {"blink": {"output_mode": "hold"}}})
    with pytest.raises(ValueError, match="gestures.blink.output_mode must be one of press, toggle, not 'hold'"):
        make(calibrate(), config)


@pytest.mark.parametrize("other", [
    {"output": "ctrl+s"},
    {"output": "ctrl", "output_mode": "toggle"},
    {"output": "shift+ctrl", "output_mode": "toggle"},
])
def test_a_held_key_cannot_be_part_of_another_output(other):
    config = hold_on_blink(nod_up=other)
    with pytest.raises(ValueError, match="gestures.blink holds ctrl down, so gestures.nod_up.output"):
        make(calibrate(), config)


def test_held_keys_may_differ_between_gestures():
    config = hold_on_blink(nod_up={"output": "shift", "output_mode": "toggle"})
    make(calibrate(), config)
