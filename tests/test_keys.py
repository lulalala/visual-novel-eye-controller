import pytest

from eyeokuri.keys import KEY_VK, KeyCombo, from_tk_event, parse_key, press_order
from eyeokuri.outputs import MOUSE_OUTPUTS, OUTPUT_NAMES, check_output_name


def test_single_key_parses():
    assert parse_key("page_down") == KeyCombo((), "page_down")


def test_combination_parses_and_is_lowercased():
    assert parse_key("Ctrl+Shift+S") == KeyCombo(("ctrl", "shift"), "s")
    assert str(parse_key(" Shift + Tab ")) == "shift+tab"


def test_lone_modifier_is_a_key():
    assert parse_key("ctrl") == KeyCombo((), "ctrl")


def test_unknown_key_is_rejected():
    with pytest.raises(ValueError, match="unknown key 'pgdn'"):
        parse_key("ctrl+pgdn")


def test_empty_part_is_rejected():
    with pytest.raises(ValueError, match="empty part"):
        parse_key("ctrl+")


def test_two_plain_keys_are_rejected():
    with pytest.raises(ValueError, match="not a modifier"):
        parse_key("a+b")


def test_repeated_modifier_is_rejected():
    with pytest.raises(ValueError, match="repeats"):
        parse_key("ctrl+ctrl+s")


def test_press_order_wraps_key_in_modifiers():
    assert press_order(parse_key("ctrl+shift+z")) == [
        ("ctrl", True), ("shift", True), ("z", True), ("z", False), ("shift", False), ("ctrl", False),
    ]


def test_common_outputs_are_all_valid():
    for name in OUTPUT_NAMES:
        assert name in MOUSE_OUTPUTS or name in KEY_VK
        check_output_name(name)
    for bad in ("app:toggle_pause", ""):
        with pytest.raises(ValueError):
            check_output_name(bad)


def test_unknown_key_message_names_every_key():
    with pytest.raises(ValueError) as e:
        parse_key("pgdn")
    message = str(e.value)
    assert "a-z, 0-9, f1-f24" in message
    for key in KEY_VK:
        if len(key) > 1 and not key[1:].isdigit():
            assert key in message


def test_letter_and_digit_codes_are_windows_virtual_keys():
    assert KEY_VK["a"] == 0x41
    assert KEY_VK["z"] == 0x5A
    assert KEY_VK["0"] == 0x30
    assert KEY_VK["f1"] == 0x70
    assert KEY_VK["f24"] == 0x87


def test_tk_events_map_to_key_names():
    assert from_tk_event("Next", 0, "win32") == "page_down"
    assert from_tk_event("F5", 0, "win32") == "f5"
    assert from_tk_event("Return", 0, "darwin") == "enter"
    # Shift turns the keysym upper case; the name stays lower case.
    assert from_tk_event("S", 0x1 | 0x4, "win32") == "ctrl+shift+s"


def test_tk_modifier_bits_differ_by_platform():
    assert from_tk_event("s", 0x20000, "win32") == "alt+s"
    assert from_tk_event("s", 0x8, "win32") == "s"  # Num Lock on Windows
    assert from_tk_event("s", 0x8, "darwin") == "win+s"  # Command
    assert from_tk_event("s", 0x8, "linux") == "alt+s"


def test_tk_lone_modifier_or_unnamed_key_gives_none():
    assert from_tk_event("Control_L", 0x4, "win32") is None
    assert from_tk_event("exclam", 0x1, "win32") is None
