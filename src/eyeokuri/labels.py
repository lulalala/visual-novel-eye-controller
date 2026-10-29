"""What the GUI shows for a gesture, signal or output mode ID. The ID stays the name
everywhere else: config files, --set, logs and trigger reasons."""

from __future__ import annotations

from eyeokuri.i18n import N_, _, aside

# Built-in gesture ID -> label; every one in config._default_gestures() needs an entry.
_GESTURES = {
    "blink": N_("Blink"),
    "wink_left": N_("Left wink"),
    "wink_right": N_("Right wink"),
    "head_shake": N_("Head shake"),
    "nod_up": N_("Nod up"),
    "nod_down": N_("Nod down"),
    "tilt_right": N_("Tilt right"),
    "tilt_left": N_("Tilt left"),
}
# Signal ID -> label; every one in config.SIGNALS needs an entry.
_SIGNALS = {
    "eyes": N_("Eye openness"),
    "wink": N_("Wink"),
    "pitch": N_("Head tilt"),
    "yaw": N_("Head turn"),
    "roll": N_("Side tilt"),
}
# Output mode ID -> label; every one in outputs.OUTPUT_MODES needs an entry.
_OUTPUT_MODES = {
    "press": N_("Press once"),
    "toggle": N_("Hold until it fires again"),
    "while": N_("Hold while it lasts"),
}


def show_gesture(name: str) -> str:
    """A built-in gesture's label, or the name of one you added."""
    return _show(name, _GESTURES.get(name))


def show_signal(signal: str) -> str:
    """A signal's label."""
    return _show(signal, _SIGNALS.get(signal))


def show_output_mode(mode: str) -> str:
    """An output mode's label."""
    return _show(mode, _OUTPUT_MODES.get(mode))


def _show(ident: str, label: str | None) -> str:
    """The label, followed by the ID unless the label already spells it
    ("Nod down" for nod_down), so you can find it in the log and config file."""
    if label is None:
        return ident
    shown = _(label)
    return shown if shown.lower().replace(" ", "_") == ident else shown + aside(ident)
