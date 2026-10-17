import pytest

from vn_eye.app import build_config, parse_args
from vn_eye.config import Config, StepConfig, dump_config, load_config


def config_from(*argv):
    return build_config(parse_args(list(argv)))


def test_defaults():
    config = config_from()
    assert config.gestures["blink"].steps[1].after_min_s == 0.15
    assert {name: g.output for name, g in config.gestures.items()} == {
        "blink": "enter",
        "head_shake": "app:toggle_pause",
        "nod_up": "up",
        "nod_down": "down",
    }
    assert config.feedback.log_rejected


def test_shortcut_flags():
    config = config_from(
        "--min-duration", "0.6", "--blink-key", "space",
        "--dry-run", "--no-sound", "--no-head-shake", "--camera", "1",
    )
    assert config.gestures["blink"].steps[1].after_min_s == 0.6
    assert config.gestures["blink"].output == "space"
    assert config.output.dry_run
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


def test_invalid_app_output_is_rejected():
    with pytest.raises(ValueError, match="gestures.blink.output"):
        config_from("--set", "gestures.blink.output=app:notacommand")


def test_invalid_gesture_is_rejected_before_the_camera_opens():
    with pytest.raises(ValueError, match="unknown gesture"):
        config_from("--set", 'gestures.blink.steps=[{gesture = "wink"}]')


def test_inverted_eye_ratios_are_rejected():
    with pytest.raises(ValueError, match="eyes.close_ratio"):
        config_from("--set", "eyes.close_ratio=0.9")


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
