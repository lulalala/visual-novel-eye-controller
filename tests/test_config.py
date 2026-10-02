import pytest

from vn_eye.app import build_config, parse_args
from vn_eye.config import LongBlinkConfig


def config_from(*argv):
    return build_config(parse_args(list(argv)))


def test_defaults():
    config = config_from()
    assert config.long_blink.min_duration_s == LongBlinkConfig().min_duration_s
    assert config.output.actions == {
        "long_blink": "enter",
        "head_shake": "app:toggle_pause",
        "head_nod_up": "up",
        "head_nod_down": "down",
        "nod_up": "up",
        "nod_down": "down",
    }
    assert config.feedback.log_blinks


def test_shortcut_flags():
    config = config_from(
        "--min-duration", "0.6", "--fire-on", "hold", "--output", "space",
        "--dry-run", "--no-sound", "--no-blink-log", "--camera", "1",
    )
    assert config.long_blink.min_duration_s == 0.6
    assert config.long_blink.fire_on == "hold"
    assert config.output.actions["long_blink"] == "space"
    assert config.output.dry_run
    assert not config.feedback.sound
    assert not config.feedback.log_blinks
    assert config.camera.index == 1


def test_set_parses_values_and_bare_strings():
    config = config_from(
        "--set", "eyes.open_ratio=0.8",
        "--set", "eyes.require_both_eyes=false",
        "--set", "long_blink.fire_on=hold",
        "--set", "output.cooldown_s=2",
    )
    assert config.eyes.open_ratio == 0.8
    assert config.eyes.require_both_eyes is False
    assert config.long_blink.fire_on == "hold"
    assert config.output.cooldown_s == 2.0


def test_set_wins_over_shortcut_and_file(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text("[long_blink]\nmin_duration_s = 0.5\nmax_duration_s = 3.0\n")
    config = config_from("-c", str(path), "--min-duration", "0.6", "--set", "long_blink.min_duration_s=0.7")
    assert config.long_blink.min_duration_s == 0.7
    assert config.long_blink.max_duration_s == 3.0


@pytest.mark.parametrize("bad", ["eyes.nope=1", "eyes.close_ratio=abc", "novalue"])
def test_bad_set_is_rejected(bad):
    with pytest.raises(ValueError):
        config_from("--set", bad)
