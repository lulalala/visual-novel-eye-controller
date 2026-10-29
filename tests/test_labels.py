import pytest

from eyeokuri import labels
from eyeokuri.config import SIGNALS, Config
from eyeokuri.i18n import set_language
from eyeokuri.labels import show_gesture, show_output_mode, show_signal
from eyeokuri.outputs import OUTPUT_MODES


@pytest.fixture(autouse=True)
def reset_language():
    yield
    set_language("en")


def test_every_built_in_gesture_and_signal_has_a_label():
    assert set(labels._GESTURES) == set(Config().gestures)
    assert set(labels._SIGNALS) == set(SIGNALS)


def test_english_label_leaves_out_an_id_it_already_spells():
    assert show_gesture("nod_down") == "Nod down"
    assert show_signal("eyes") == "Eyes"


def test_english_label_shows_an_id_it_doesnt_spell():
    assert show_gesture("wink_left") == "Left wink (wink_left)"
    assert show_signal("yaw") == "Head turn (yaw)"


def test_translated_label_shows_the_id_in_full_width_parentheses():
    set_language("ja")
    assert show_gesture("blink") == "まばたき（blink）"
    set_language("zh-TW")
    assert show_signal("pitch") == "頭部俯仰（pitch）"


def test_a_gesture_you_added_shows_its_name():
    set_language("ja")
    assert show_gesture("double_blink") == "double_blink"


def test_every_output_mode_has_a_label():
    assert set(labels._OUTPUT_MODES) == set(OUTPUT_MODES)
    assert show_output_mode("while") == "Hold while it lasts (while)"
