import pytest

from vn_eye.app import build_config, parse_args
from vn_eye.config import BlinkConfig


def config_from(*argv):
    return build_config(parse_args(list(argv)))


def test_defaults():
    config = config_from()
    assert config.blink.min_duration_s == BlinkConfig().min_duration_s
    assert config.output.actions == {
        "blink": "enter",
        "head_shake": "app:toggle_pause",
        "head_nod_up": "up",
        "head_nod_down": "down",
        "nod_up": "up",
        "nod_down": "down",
    }
    assert config.feedback.log_rejected


def test_shortcut_flags():
    config = config_from(
        "--min-duration", "0.6", "--output", "space",
        "--dry-run", "--no-sound", "--no-rejected-log", "--camera", "1",
    )
    assert config.blink.min_duration_s == 0.6
    assert config.output.actions["blink"] == "space"
    assert config.output.dry_run
    assert not config.feedback.sound
    assert not config.feedback.log_rejected
    assert config.camera.index == 1


def test_set_parses_values_and_bare_strings():
    config = config_from(
        "--set", "eyes.open_ratio=0.8",
        "--set", "eyes.require_both_eyes=false",
        "--set", "output.actions.blink=space",
        "--set", "output.cooldown_s=2",
    )
    assert config.eyes.open_ratio == 0.8
    assert config.eyes.require_both_eyes is False
    assert config.output.actions["blink"] == "space"
    assert config.output.cooldown_s == 2.0


def test_set_wins_over_shortcut_and_file(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text("[blink]\nmin_duration_s = 0.5\nmax_duration_s = 3.0\n")
    config = config_from("-c", str(path), "--min-duration", "0.6", "--set", "blink.min_duration_s=0.7")
    assert config.blink.min_duration_s == 0.7
    assert config.blink.max_duration_s == 3.0


@pytest.mark.parametrize("bad", ["eyes.nope=1", "eyes.close_ratio=abc", "novalue"])
def test_bad_set_is_rejected(bad):
    with pytest.raises(ValueError):
        config_from("--set", bad)


def test_invalid_keystroke_action_is_rejected():
    with pytest.raises(ValueError, match="output.actions"):
        config_from("--set", "output.actions.blink=notakey")


def test_invalid_app_action_is_rejected():
    with pytest.raises(ValueError, match="output.actions"):
        config_from("--set", "output.actions.blink=app:notacommand")


def test_inverted_eye_ratios_are_rejected():
    with pytest.raises(ValueError, match="eyes.close_ratio"):
        config_from("--set", "eyes.close_ratio=0.9")
