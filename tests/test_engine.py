from dataclasses import replace

from vn_eye.config import Config, apply_overrides
from vn_eye.engine import Engine
from vn_eye.sources import EYE_OPENNESS, HEAD_POSE, Signals

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
        return Signals(t, face_present=True, eye_openness=(eyes, eyes), head_yaw_deg=yaw, head_pitch_deg=0.0)

    def debug_view(self):
        return None

    def close(self):
        pass


class RecordingOutput:
    def __init__(self):
        self.sent = []

    def send(self, name):
        self.sent.append(name)


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


def test_head_shake_pauses_and_blinks_are_then_ignored():
    samples = calibrate() + shake() + blink()
    engine, output, messages, sounds = make(samples)
    run(engine, len(samples))
    assert engine.paused
    assert output.sent == []
    assert "Paused" in messages
    assert any(m.endswith("-> ignored (paused)") for m in messages)


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
