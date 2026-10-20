"""Key names for outputs: parsing "ctrl+s" style names and the order to press them in."""

from __future__ import annotations

from dataclasses import dataclass

MODIFIERS = ("ctrl", "shift", "alt", "win")

# Key name -> Windows virtual-key code. Win32Output turns the code into a
# scan code for the current keyboard layout, so "a" is whichever key types a.
KEY_VK: dict[str, int] = {
    **{chr(c): ord(chr(c).upper()) for c in range(ord("a"), ord("z") + 1)},
    **{str(d): 0x30 + d for d in range(10)},
    **{f"f{n}": 0x6F + n for n in range(1, 25)},
    "enter": 0x0D,
    "space": 0x20,
    "tab": 0x09,
    "escape": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "page_up": 0x21,
    "page_down": 0x22,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "shift": 0x10,
    "ctrl": 0x11,
    "alt": 0x12,
    "win": 0x5B,
}

# Keys that Windows sends with the 0xE0 prefix (KEYEVENTF_EXTENDEDKEY).
# Without it the navigation keys would act as their number-pad twins.
EXTENDED_KEYS = frozenset({
    "delete", "insert", "home", "end", "page_up", "page_down", "left", "up", "right", "down", "win",
})

_KEY_HELP = "a-z, 0-9, f1-f24, enter, space, tab, escape, backspace, delete, insert, home, end, " \
    "page_up, page_down, up, down, left, right, ctrl, shift, alt, win"


@dataclass(frozen=True)
class KeyCombo:
    modifiers: tuple[str, ...]
    key: str

    def __str__(self) -> str:
        return "+".join((*self.modifiers, self.key))


def parse_key(text: str) -> KeyCombo:
    """Parses "ctrl+s" style names; raises ValueError naming the bad part."""
    parts = text.strip().lower().split("+")
    if any(p.strip() == "" for p in parts):
        raise ValueError(f"empty part in key {text!r}; write keys like ctrl+s")
    parts = [p.strip() for p in parts]
    *modifiers, key = parts
    for part in parts:
        if part not in KEY_VK:
            raise ValueError(f"unknown key {part!r} in {text!r}; use {_KEY_HELP} (e.g. ctrl+s)")
    for m in modifiers:
        if m not in MODIFIERS:
            raise ValueError(f"{m!r} in {text!r} is not a modifier; only the last part can be "
                             f"another key, and modifiers are {', '.join(MODIFIERS)}")
    if len(set(parts)) != len(parts):
        raise ValueError(f"key {text!r} repeats a key")
    return KeyCombo(tuple(modifiers), key)


def press_order(combo: KeyCombo) -> list[tuple[str, bool]]:
    """(key, down) events: modifiers down, key down and up, modifiers up in reverse."""
    return [
        *((m, True) for m in combo.modifiers),
        (combo.key, True),
        (combo.key, False),
        *((m, False) for m in reversed(combo.modifiers)),
    ]


_TK_KEYSYMS = {
    "Return": "enter", "KP_Enter": "enter", "space": "space", "Tab": "tab", "ISO_Left_Tab": "tab",
    "Escape": "escape", "BackSpace": "backspace", "Delete": "delete", "Insert": "insert",
    "Home": "home", "End": "end", "Prior": "page_up", "Next": "page_down",
    "Left": "left", "Up": "up", "Right": "right", "Down": "down",
}
_TK_MODIFIER_KEYSYMS = frozenset({
    "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Meta_L", "Meta_R",
    "Super_L", "Super_R", "Win_L", "Win_R", "Option_L", "Option_R", "Command", "Caps_Lock",
})
# Tk's event.state bits for each modifier differ by platform.
_TK_STATE_MASKS = {
    "win32": {"ctrl": 0x4, "shift": 0x1, "alt": 0x20000},
    "darwin": {"ctrl": 0x4, "shift": 0x1, "alt": 0x10, "win": 0x8},
    "other": {"ctrl": 0x4, "shift": 0x1, "alt": 0x8, "win": 0x40},
}


def from_tk_event(keysym: str, state: int, platform: str) -> str | None:
    """The output name for a Tk key press, or None for a lone modifier or an unnamed key."""
    if keysym in _TK_MODIFIER_KEYSYMS:
        return None
    if len(keysym) == 1 and keysym.isascii() and keysym.isalnum():
        key = keysym.lower()
    elif keysym[:1] == "F" and keysym[1:].isdigit() and keysym.lower() in KEY_VK:
        key = keysym.lower()
    else:
        key = _TK_KEYSYMS.get(keysym)
        if key is None:
            return None
    masks = _TK_STATE_MASKS.get(platform, _TK_STATE_MASKS["other"])
    modifiers = tuple(m for m in MODIFIERS if m in masks and state & masks[m])
    return str(KeyCombo(modifiers, key))
