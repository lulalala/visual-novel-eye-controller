from dataclasses import replace

import pytest

from eyeokuri.config import Config, GestureConfig, StepConfig
from eyeokuri.eyes import Observation
from eyeokuri.tuning import DO, OTHER, TOO_QUICK, TOO_SLOW, Take, can_tune, fit, script, suggestions, trim

FPS = 30


def obs(i, eyes=1.0, yaw=0.0, pitch=0.0):
    return Observation(i / FPS, face_present=True, ready=True, combined=eyes, baseline=1.0,
                       head_yaw=yaw, head_pitch=pitch)


def blink_take(kind, closed_frames, depth=0.2, total=90):
    """Open for 15 frames, closed for closed_frames, then open until total."""
    values = [1.0] * 15 + [depth] * closed_frames
    values += [1.0] * max(total - len(values), 0)
    return Take(kind, [obs(i, eyes=v) for i, v in enumerate(values[:total])])


def head_take(kind, values, axis):
    return Take(kind, [obs(i, **{axis: v}) for i, v in enumerate(values)])


def blink_takes():
    return [
        *(blink_take(DO, n) for n in (12, 13, 14, 15, 16)),
        *(blink_take(TOO_QUICK, n, depth=0.3) for n in (3, 4, 4)),
        *(blink_take(TOO_SLOW, 200, total=150) for _ in range(2)),
    ]


def test_blink_fits_between_your_blinks_and_the_near_misses():
    result = fit(Config(), "blink", blink_takes())
    close, reopen = result.gesture.steps
    # 60% of the way from 1.0 to your weakest blink (0.2).
    assert close.below_ratio == 0.52
    # Between the quick blinks (4 frames) and your quickest (12 frames).
    assert 4 / FPS < reopen.after_min_s < 12 / FPS
    # Above your slowest blink (16 frames), below the closures cut off at the end.
    assert 16 / FPS < reopen.after_max_s < 135 / FPS
    assert [r.fired_at is not None for r in result.results] == [True] * 5 + [False] * 5


def test_blink_takes_keep_the_open_edge():
    result = fit(Config(), "blink", blink_takes())
    assert result.gesture.steps[1].above_ratio == 0.75


def test_a_take_with_hardly_any_movement_is_left_out():
    takes = blink_takes()
    takes[2] = blink_take(DO, 14, depth=0.9)
    result = fit(Config(), "blink", takes)
    assert result.gesture.steps[0].below_ratio == 0.52
    assert any(n.startswith("take 3: hardly any movement") for n in result.notes)
    assert result.results[2].fired_at is None


def test_takes_without_movement_leave_the_edges_alone():
    result = fit(Config(), "blink", [blink_take(DO, 0) for _ in range(5)])
    assert result.gesture.steps[0].below_ratio == 0.55
    assert any("hardly moved eyes" in n for n in result.notes)


def test_an_edge_stays_clear_of_the_box_around_rest():
    # Nods that reach 14°: 60% would be 8.4°, too close to the ±8° center box.
    nod = [0.0] * 10 + [7.0, 14.0, 14.0, 7.0] + [0.0] * 20
    takes = [head_take(DO, nod, "pitch") for _ in range(5)]
    result = fit(Config(), "nod_down", takes)
    assert result.gesture.steps[0].above_deg == 11.0
    assert all(r.fired_at is not None for r in result.results)


def test_takes_that_cannot_reach_the_edge_are_reported():
    nod = [0.0] * 10 + [5.0, 10.0, 10.0, 5.0] + [0.0] * 20
    result = fit(Config(), "nod_down", [head_take(DO, nod, "pitch") for _ in range(3)])
    assert result.gesture.steps[0].above_deg == 11.0
    assert any("weakest take didn't reach the edge" in n for n in result.notes)
    assert all(r.fired_at is None for r in result.results)


def test_head_shake_fits_its_edges_and_whole_gesture_time():
    quick = [0.0] * 10 + [12.0, 25.0, 12.0, 0.0, -12.0, -25.0, -12.0] + [0.0] * 20
    slow = [0.0] * 10 + [25.0] * 45 + [0.0] * 10 + [-25.0] * 20 + [0.0] * 10
    takes = [*(head_take(DO, quick, "yaw") for _ in range(5)), *(head_take(TOO_SLOW, slow, "yaw") for _ in range(2))]
    result = fit(Config(), "head_shake", takes)
    left, right = result.gesture.steps
    assert (left.above_deg, right.below_deg) == (15.0, -15.0)
    assert 4 / FPS < result.gesture.within_s < 2.0
    # Limits that were off stay off.
    assert left.after_max_s == right.after_max_s == 0.0
    assert [r.fired_at is not None for r in result.results] == [True] * 5 + [False] * 2


def test_near_misses_that_overlap_your_takes_are_reported():
    takes = [*(blink_take(DO, n) for n in (6, 12, 14)), blink_take(TOO_QUICK, 8)]
    result = fit(Config(), "blink", takes)
    assert result.gesture.steps[1].after_min_s < 6 / FPS
    assert any("too-quick take(s) were as slow as your quickest" in n for n in result.notes)
    assert result.results[3].fired_at is not None


def test_without_any_matching_take_the_timing_stays():
    takes = [blink_take(DO, 200, total=60) for _ in range(3)]
    result = fit(Config(), "blink", takes)
    default = Config().gestures["blink"].steps[1]
    assert (result.gesture.steps[1].after_min_s, result.gesture.steps[1].after_max_s) == (
        default.after_min_s, default.after_max_s)
    assert any("the gesture wasn't found" in n for n in result.notes)


def test_other_takes_are_only_checked():
    takes = [*(blink_take(DO, 14) for _ in range(3)), blink_take(OTHER, 13)]
    result = fit(Config(), "blink", takes)
    # A normal-length blink while reading still fires: the wizard reports it.
    assert result.results[3].fired_at is not None


def test_gestures_made_of_other_gestures_cannot_be_tuned():
    double = GestureConfig(steps=[StepConfig(gesture="blink"), StepConfig(gesture="blink", after_max_s=1.0)])
    config = replace(Config(), gestures={**Config().gestures, "double": double})
    assert not can_tune(double)
    assert can_tune(Config().gestures["blink"])
    with pytest.raises(ValueError, match="gestures.double"):
        fit(config, "double", [])


def test_every_gesture_suggests_takes_that_fire_and_near_misses():
    for name in [*Config().gestures, "custom"]:
        kinds = [kind for kind, _ in suggestions(name)]
        assert kinds[0] == DO and len(kinds) > 1


def test_script_asks_for_the_gesture_several_times_then_each_near_miss_once():
    kinds = [kind for kind, _ in script("blink", do_takes=3)]
    assert kinds == [DO, DO, DO, TOO_QUICK, TOO_SLOW]


def test_trim_keeps_a_fifth_of_a_second_around_the_movement_and_restarts_the_clock():
    values = [1.0] * 60 + [0.2] * 12 + [1.0] * 78  # closed from frame 60 to 71
    observations = [obs(i, eyes=v) for i, v in enumerate(values)]
    start, cut = trim(observations, {"eyes"})
    assert start == pytest.approx(60 / FPS - 0.2)
    assert cut[0].timestamp == pytest.approx(0.0)
    assert cut[-1].timestamp == pytest.approx(71 / FPS + 0.2 - start)


def test_trim_skips_a_half_blink_before_the_real_one():
    # Half open (0.7) at 0.2 s, then the blink (0.1) at 1.25 s.
    values = [1.0] * 6 + [0.7] * 6 + [1.0] * 25 + [0.1] * 5 + [1.0] * 48
    observations = [obs(i, eyes=v) for i, v in enumerate(values)]
    start, cut = trim(observations, {"eyes"})
    assert start == pytest.approx(37 / FPS - 0.2)
    assert all(o.combined != 0.7 for o in cut)


def test_trim_keeps_a_take_without_movement_whole():
    take = blink_take(OTHER, 0)
    assert trim(take.observations, {"eyes"}) == (0.0, take.observations)
