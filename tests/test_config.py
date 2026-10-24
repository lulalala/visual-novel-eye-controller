import pytest

from eyeokuri.app import build_config, parse_args
from eyeokuri.config import Config, StepConfig, dump_config, load_config


def config_from(*argv):
    return build_config(parse_args(list(argv)))


def test_defaults():
    config = config_from()
    assert config.gestures["blink"].steps[1].after_min_s == 0.1
    assert {name: g.output for name, g in config.gestures.items()} == {
        "blink": "enter",
        "wink_left": "",
        "wink_right": "",
        "head_shake": "app:toggle_pause",
        "nod_up": "up",
        "nod_down": "down",
    }
    assert config.feedback.log_rejected


def test_shortcut_flags():
    config = config_from(
        "--min-duration", "0.6", "--blink-key", "space",
        "--no-sound", "--no-head-shake", "--camera", "1",
    )
    assert config.gestures["blink"].steps[1].after_min_s == 0.6
    assert config.gestures["blink"].output == "space"
    assert not config.feedback.sound
    assert not config.gestures["head_shake"].enabled
    assert config.camera.index == 1


def test_set_parses_values_and_bare_strings():
    config = config_from(
        "--set", "eyes.open_ratio=0.8",
        "--set", "eyes.require_both_eyes=false",
        "--set", "gestures.blink.output=space",
        "--set", "gestures.blink.cooldown_s=2",
    )
    assert config.eyes.open_ratio == 0.8
    assert config.eyes.require_both_eyes is False
    assert config.gestures["blink"].output == "space"
    assert config.gestures["blink"].cooldown_s == 2.0


def test_set_changes_one_step_by_index():
    config = config_from("--set", "gestures.nod_down.steps.0.above_deg=15")
    steps = config.gestures["nod_down"].steps
    assert steps[0].above_deg == 15.0
    assert steps[1] == Config().gestures["nod_down"].steps[1]


def test_set_adds_a_new_gesture():
    config = config_from(
        "--set", 'gestures.look.steps=[{signal = "yaw", above_deg = 20, hold_s = 1}]',
        "--set", "gestures.look.output=space",
    )
    assert config.gestures["look"].steps == [StepConfig(signal="yaw", above_deg=20.0, hold_s=1.0)]


def test_set_wins_over_shortcut_and_file(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text(
        "version = 1\n[gestures.blink]\nsteps = [\n"
        '  { signal = "eyes", below_ratio = 0.5 },\n'
        '  { signal = "eyes", above_ratio = 0.8, after_min_s = 0.5, after_max_s = 3.0 },\n'
        "]\n"
    )
    config = config_from("-c", str(path), "--min-duration", "0.6", "--set", "gestures.blink.steps.1.after_min_s=0.7")
    blink = config.gestures["blink"]
    assert blink.steps[1].after_min_s == 0.7
    assert blink.steps[1].after_max_s == 3.0
    assert blink.steps[0].below_ratio == 0.5
    # Fields the file doesn't set keep the built-in gesture's values.
    assert blink.output == "enter"


def test_file_without_version_is_rejected(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text("[blink]\nmin_duration_s = 0.5\n")
    with pytest.raises(ValueError, match="config.example.toml"):
        config_from("-c", str(path))


def test_example_config_matches_defaults():
    config = config_from("-c", "config.example.toml")
    assert config == Config()


@pytest.mark.parametrize("bad", [
    "eyes.nope=1", "eyes.close_ratio=abc", "novalue", "gestures.blink.nope=1", "gestures.blink=1",
    "gestures.blink.steps.5.hold_s=1", "gestures.blink.steps.0.nope=1", "gestures.blink.steps=1",
    "gestures.blink.steps.0.above_ratio=abc",
])
def test_bad_set_is_rejected(bad):
    with pytest.raises(ValueError):
        config_from("--set", bad)


def test_invalid_keystroke_output_is_rejected():
    with pytest.raises(ValueError, match="gestures.blink.output"):
        config_from("--set", "gestures.blink.output=notakey")


def test_key_combination_output_is_accepted():
    config = config_from("--set", "gestures.blink.output=ctrl+s", "--set", "gestures.nod_up.output=page_down")
    assert config.gestures["blink"].output == "ctrl+s"
    assert config.gestures["nod_up"].output == "page_down"


def test_blink_key_flag_accepts_any_key():
    assert config_from("--blink-key", "F5").gestures["blink"].output == "f5"


def test_blink_key_flag_rejects_unknown_key(capsys):
    with pytest.raises(SystemExit):
        config_from("--blink-key", "ctrl+zz")
    assert "unknown key 'zz'" in capsys.readouterr().err


def test_invalid_app_output_is_rejected():
    with pytest.raises(ValueError, match="gestures.blink.output"):
        config_from("--set", "gestures.blink.output=app:notacommand")


def test_invalid_gesture_is_rejected_before_the_camera_opens():
    with pytest.raises(ValueError, match="unknown gesture"):
        config_from("--set", 'gestures.blink.steps=[{gesture = "wink"}]')


def test_inverted_eye_ratios_are_rejected():
    with pytest.raises(ValueError, match="eyes.close_ratio"):
        config_from("--set", "eyes.close_ratio=0.9")


def test_eye_warmup_longer_than_the_window_is_rejected():
    with pytest.raises(ValueError, match="eyes.warmup_s"):
        config_from("--set", "eyes.warmup_s=12")
    with pytest.raises(ValueError, match="eyes.warmup_s"):
        config_from("--set", "eyes.baseline_window_s=1.5")


def test_head_window_must_be_above_zero():
    with pytest.raises(ValueError, match="head.baseline_window_s"):
        config_from("--set", "head.baseline_window_s=0")


def test_dump_of_defaults_is_only_the_version():
    assert dump_config(Config()) == "version = 1\n"


def test_dump_reads_back_as_the_same_config(tmp_path):
    config = config_from(
        "--camera", "1", "--min-duration", "0.4",
        "--set", "gestures.head_shake.enabled=false",
        "--set", 'gestures.look.steps=[{signal = "yaw", above_deg = 20, hold_s = 1}]',
        "--set", "gestures.look.output=space",
        "--set", 'gestures."two words".steps=[{gesture = "blink"}]',
    )
    path = tmp_path / "saved.toml"
    path.write_text(dump_config(config))
    assert load_config(path) == config


def test_dump_writes_only_what_changed_in_a_built_in_gesture():
    text = dump_config(config_from("--set", "gestures.blink.output=space"))
    assert text == 'version = 1\n\n[gestures.blink]\noutput = "space"\n'


def test_guards_can_be_changed_with_set_and_survive_a_dump(tmp_path):
    config = config_from("--set", "gestures.blink.guards.0.below_deg=30")
    assert config.gestures["blink"].guards[0].below_deg == 30.0
    path = tmp_path / "saved.toml"
    path.write_text(dump_config(config))
    assert load_config(path) == config


def test_tiny_camera_size_is_rejected():
    with pytest.raises(ValueError, match="camera.width"):
        build_config(parse_args(["--set", "camera.width=1"]))
    with pytest.raises(ValueError, match="camera.height"):
        build_config(parse_args(["--set", "camera.height=1"]))


def test_step_unit_and_bounds_follow_the_signal():
    eyes = StepConfig(signal="eyes", above_ratio=0.75)
    head = StepConfig(signal="yaw", above_deg=-5.0, below_deg=5.0)
    assert (eyes.unit, eyes.bounds) == ("ratio", (0.75, None))
    assert (head.unit, head.bounds) == ("deg", (-5.0, 5.0))


def test_paused_survives_a_dump_and_works_with_set(tmp_path):
    config = config_from("--set", "app.paused=true")
    assert config.app.paused
    text = dump_config(config)
    assert text == "version = 1\n\n[app]\npaused = true\n"
    path = tmp_path / "saved.toml"
    path.write_text(text)
    assert load_config(path) == config


def test_language_can_be_set_through_set():
    assert config_from("--set", "app.language=en").app.language == "en"
    assert config_from("--set", "app.language=ja").app.language == "ja"
    assert config_from("--set", "app.language=zh-TW").app.language == "zh-TW"


def test_unknown_language_is_rejected():
    with pytest.raises(ValueError, match="app.language must be one of auto, en, ja, zh-TW"):
        config_from("--set", "app.language=fr")
