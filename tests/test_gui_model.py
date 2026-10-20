import pytest

from eyeokuri.config import SIGNALS, Config, GestureConfig, StepConfig
from eyeokuri.eyes import Observation
from eyeokuri.gui.model import (
    GESTURE_NAME, SIGNAL_PLOTS, fmt, gesture_config, gesture_model, new_step, users_of,
)
from eyeokuri.gui.worker import state_text


@pytest.mark.parametrize("name", list(Config().gestures))
def test_built_in_gestures_survive_the_editor_round_trip(name):
    gesture = Config().gestures[name]
    assert gesture_config(gesture_model(gesture)) == gesture


def test_gesture_steps_survive_the_editor_round_trip():
    gesture = GestureConfig(
        steps=[StepConfig(signal="yaw", above_deg=15.0, hold_s=0.2), StepConfig(gesture="blink", after_max_s=1.0)],
        guards=[StepConfig(signal="pitch", above_deg=-10.0, below_deg=10.0)],
    )
    assert gesture_config(gesture_model(gesture)) == gesture


def test_plot_table_covers_every_signal():
    # Adding a signal to config.SIGNALS needs a plot lane too.
    assert set(SIGNAL_PLOTS) == set(SIGNALS)


def test_plot_highlights_the_same_rest_value_that_tuning_uses():
    from eyeokuri import tuning

    for signal, plot in SIGNAL_PLOTS.items():
        assert plot.zero == tuning._REST[signal]
        assert plot.lo < plot.zero < plot.hi
        assert plot.zero in plot.grid


def test_new_step_has_a_box_for_each_signal():
    for signal in SIGNALS:
        step = new_step(signal)
        assert step["kind"] == signal
        assert step["above"] is not None or step["below"] is not None
    assert new_step("gesture")["above"] is None


def test_fmt_leaves_empty_for_no_limit():
    assert fmt(None) == ""
    assert fmt(0.55) == "0.55"
    assert fmt(12.0) == "12"


def test_gesture_names_allow_letters_digits_underscore_and_dash():
    assert GESTURE_NAME.fullmatch("nod_up-2")
    assert not GESTURE_NAME.fullmatch("nod up")
    assert not GESTURE_NAME.fullmatch("")


def test_state_text_names_the_most_important_state():
    open_eyes = Observation(0.0, face_present=True, ready=True)
    assert state_text(open_eyes, paused=False, suspended=False, fps=30.0).startswith("Watching")
    assert state_text(open_eyes, paused=True, suspended=False, fps=30.0).startswith("Paused")
    assert state_text(open_eyes, paused=True, suspended=True, fps=30.0).startswith("Gestures off")
    assert state_text(Observation(0.0, face_present=False), False, False, 30.0).startswith("No face")
    assert state_text(Observation(0.0, face_present=True), False, False, 30.0).startswith("Calibrating")
    closed = Observation(0.0, face_present=True, ready=True, closed=True)
    assert state_text(closed, False, False, 30.0).startswith("Eyes closed")


def test_users_of_lists_the_gestures_that_use_one_as_a_step():
    gestures = {
        **Config().gestures,
        "blink_then_nod": GestureConfig(steps=[StepConfig(gesture="blink"), StepConfig(gesture="nod_down")]),
        "double_blink": GestureConfig(steps=[StepConfig(gesture="blink"), StepConfig(gesture="blink")]),
    }
    assert users_of(gestures, "blink") == ["blink_then_nod", "double_blink"]
    assert users_of(gestures, "nod_down") == ["blink_then_nod"]
    assert users_of(gestures, "head_shake") == []
