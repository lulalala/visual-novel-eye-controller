import pytest

from eyeokuri.config import SIGNALS, CameraConfig, Config, GestureConfig, StepConfig
from eyeokuri.eyes import Observation
from eyeokuri.gui.model import (
    GESTURE_NAME, RECORD_S, SIGNAL_PLOTS, find_notice_file, fmt, gesture_config, gesture_model, new_step, users_of, view_size,
    wizard_traces,
)
from eyeokuri.gui.worker import state_text
from eyeokuri.triggers import Replay
from eyeokuri.tuning import DO, Take


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


def test_plot_has_a_grid_line_at_each_signals_rest_value():
    for signal, plot in SIGNAL_PLOTS.items():
        rest = SIGNALS[signal].rest
        assert plot.lo < rest < plot.hi
        assert rest in plot.grid


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


def test_camera_view_is_the_camera_frame_size():
    assert view_size(Config().camera) == (640, 480)


def test_wide_camera_frames_are_scaled_down_for_the_view():
    assert view_size(CameraConfig(width=1280, height=720)) == (640, 360)


def test_notice_file_is_found_in_the_first_folder_that_has_it(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (second / "LICENSE").write_text("text")
    assert find_notice_file("LICENSE", [first, second]) == second / "LICENSE"


def test_missing_notice_file_gives_none(tmp_path):
    assert find_notice_file("LICENSE", [tmp_path]) is None


def _eyes(count, eyes=1.0):
    return [Observation(i / 30, face_present=True, ready=True, combined=eyes, baseline=1.0) for i in range(count)]


def test_wizard_plot_shows_the_raw_trace_while_recording():
    live = _eyes(45, eyes=0.2)
    traces = wizard_traces([None], {}, picked=None, signals={"eyes"}, on_review=False, live=live)
    assert traces.main == live
    assert traces.result is None
    assert traces.duration == RECORD_S


def test_wizard_plot_stretches_to_a_long_recording():
    traces = wizard_traces([None], {}, picked=None, signals={"eyes"}, on_review=False, live=_eyes(30 * 6))
    assert traces.duration == 6.0


def test_wizard_plot_keeps_earlier_takes_behind_the_recording():
    earlier = Take(DO, _eyes(30, eyes=0.2))
    result = Replay(None, "no step matched", ())
    traces = wizard_traces([earlier, None], {0: result}, picked=1, signals={"eyes"}, on_review=False, live=_eyes(10))
    assert len(traces.others) == 1


def test_wizard_plot_hides_the_step_boxes_while_recording():
    assert not wizard_traces([None], {}, picked=None, signals={"eyes"}, on_review=False, live=_eyes(10)).boxes


def test_wizard_plot_shows_the_step_boxes_for_a_finished_take():
    take = Take(DO, _eyes(30, eyes=0.2))
    result = Replay(None, "no step matched", ())
    assert wizard_traces([take], {0: result}, picked=0, signals={"eyes"}, on_review=False).boxes
