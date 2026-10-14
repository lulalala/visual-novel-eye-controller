import pytest

from vn_eye.app import build_config, parse_args
from vn_eye.config import Config, GestureConfig


def config_from(*argv):
    return build_config(parse_args(list(argv)))


def test_defaults():
    config = config_from()
    assert config.gestures["blink"].gap_min_s == Config().gestures["blink"].gap_min_s
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
    assert config.gestures["blink"].gap_min_s == 0.6
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
        "--set", 'gestures.blink.steps=["eyes_closed", "eyes_closed"]',
    )
    assert config.eyes.open_ratio == 0.8
    assert config.eyes.require_both_eyes is False
    assert config.gestures["blink"].output == "space"
    assert config.gestures["blink"].cooldown_s == 2.0
    assert config.gestures["blink"].steps == ["eyes_closed", "eyes_closed"]


def test_set_adds_a_new_gesture_with_defaults():
    config = config_from("--set", 'gestures.look.steps=["head_left"]', "--set", "gestures.look.output=space")
    look = config.gestures["look"]
    assert look.steps == ["head_left"]
    assert look.past_deg == GestureConfig().past_deg


def test_set_wins_over_shortcut_and_file(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text("version = 1\n[gestures.blink]\ngap_min_s = 0.5\ngap_max_s = 3.0\n")
    config = config_from("-c", str(path), "--min-duration", "0.6", "--set", "gestures.blink.gap_min_s=0.7")
    assert config.gestures["blink"].gap_min_s == 0.7
    assert config.gestures["blink"].gap_max_s == 3.0
    # Fields the file doesn't set keep the built-in gesture's values.
    assert config.gestures["blink"].steps == ["eyes_closed", "eyes_open"]


def test_file_without_version_is_rejected(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text("[blink]\nmin_duration_s = 0.5\n")
    with pytest.raises(ValueError, match="config.example.toml"):
        config_from("-c", str(path))


def test_example_config_matches_defaults():
    config = config_from("-c", "config.example.toml")
    assert config == Config()


@pytest.mark.parametrize("bad", ["eyes.nope=1", "eyes.close_ratio=abc", "novalue",
                                 "gestures.blink.nope=1", "gestures.blink=1"])
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
    with pytest.raises(ValueError, match="unknown step"):
        config_from("--set", 'gestures.blink.steps=["wink"]')


def test_inverted_eye_ratios_are_rejected():
    with pytest.raises(ValueError, match="eyes.close_ratio"):
        config_from("--set", "eyes.close_ratio=0.9")
