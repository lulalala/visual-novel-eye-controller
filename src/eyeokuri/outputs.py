"""Sending input to the game.

On Windows we call ``SendInput`` with hardware scan codes, which reaches
DirectInput/raw-input games that ignore virtual-key-only events. Elsewhere
(macOS, used for development) we go through pynput.
"""

from __future__ import annotations

import sys
import time
from typing import Callable, Protocol

from eyeokuri.triggers import TriggerEvent

OUTPUT_NAMES = ("enter", "space", "left_click", "right_click", "wheel_down", "up", "down")

# Some engines poll key state once per frame, so hold keys down briefly.
_PRESS_DURATION_S = 0.03


class Output(Protocol):
    def send(self, name: str) -> None: ...


class Win32Output:
    _SCAN_CODES = {"enter": 0x1C, "space": 0x39, "up": 0x48, "down": 0x50}
    # Arrow keys are extended keys and need KEYEVENTF_EXTENDEDKEY.
    _EXTENDED_KEYS = frozenset({"up", "down"})

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        ulong_ptr = ctypes.c_size_t

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", wintypes.LONG),
                ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ulong_ptr),
            ]

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ulong_ptr),
            ]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [
                ("uMsg", wintypes.DWORD),
                ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD),
            ]

        class _INPUTUNION(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

        class INPUT(ctypes.Structure):
            _anonymous_ = ("u",)
            _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

        self._ctypes = ctypes
        self._INPUT = INPUT
        self._KEYBDINPUT = KEYBDINPUT
        self._MOUSEINPUT = MOUSEINPUT
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
        self._user32.SendInput.restype = wintypes.UINT

    def send(self, name: str) -> None:
        if name in self._SCAN_CODES:
            scan = self._SCAN_CODES[name]
            extended = name in self._EXTENDED_KEYS
            self._key(scan, up=False, extended=extended)
            time.sleep(_PRESS_DURATION_S)
            self._key(scan, up=True, extended=extended)
        elif name == "left_click":
            self._mouse(0x0002)  # MOUSEEVENTF_LEFTDOWN
            time.sleep(_PRESS_DURATION_S)
            self._mouse(0x0004)  # MOUSEEVENTF_LEFTUP
        elif name == "right_click":
            self._mouse(0x0008)  # MOUSEEVENTF_RIGHTDOWN
            time.sleep(_PRESS_DURATION_S)
            self._mouse(0x0010)  # MOUSEEVENTF_RIGHTUP
        elif name == "wheel_down":
            # MOUSEEVENTF_WHEEL; one notch = WHEEL_DELTA (120), negative = towards user.
            self._mouse(0x0800, data=-120 & 0xFFFFFFFF)
        else:
            raise ValueError(f"Unknown output: {name}")

    def _key(self, scan: int, up: bool, extended: bool = False) -> None:
        flags = 0x0008 | (0x0002 if up else 0) | (0x0001 if extended else 0)
        inp = self._INPUT(type=1, ki=self._KEYBDINPUT(wVk=0, wScan=scan, dwFlags=flags))
        self._send(inp)

    def _mouse(self, flags: int, data: int = 0) -> None:
        inp = self._INPUT(type=0, mi=self._MOUSEINPUT(mouseData=data, dwFlags=flags))
        self._send(inp)

    def _send(self, inp: object) -> None:
        sent = self._user32.SendInput(1, self._ctypes.byref(inp), self._ctypes.sizeof(inp))
        if sent != 1:
            err = self._ctypes.get_last_error()
            # Usually UIPI: the game runs as administrator and we don't.
            print(
                f"SendInput failed (error {err}). If the game runs as administrator, "
                "run eyeokuri as administrator too.",
                file=sys.stderr,
                flush=True,
            )


class PynputOutput:
    def __init__(self) -> None:
        from pynput import keyboard, mouse

        self._keyboard = keyboard.Controller()
        self._mouse = mouse.Controller()
        self._keys = {
            "enter": keyboard.Key.enter,
            "space": keyboard.Key.space,
            "up": keyboard.Key.up,
            "down": keyboard.Key.down,
        }
        self._buttons = {"left_click": mouse.Button.left, "right_click": mouse.Button.right}

    def send(self, name: str) -> None:
        if name in self._keys:
            key = self._keys[name]
            self._keyboard.press(key)
            time.sleep(_PRESS_DURATION_S)
            self._keyboard.release(key)
        elif name in self._buttons:
            button = self._buttons[name]
            self._mouse.press(button)
            time.sleep(_PRESS_DURATION_S)
            self._mouse.release(button)
        elif name == "wheel_down":
            self._mouse.scroll(0, -1)
        else:
            raise ValueError(f"Unknown output: {name}")


def macos_accessibility_trusted() -> bool:
    """Whether this process may post input events (System Settings → Accessibility)."""
    import ctypes
    import ctypes.util

    lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("ApplicationServices"))
    lib.AXIsProcessTrusted.restype = ctypes.c_bool
    return bool(lib.AXIsProcessTrusted())


def create_output() -> Output:
    if sys.platform == "win32":
        return Win32Output()
    if sys.platform == "darwin" and not macos_accessibility_trusted():
        # Without this permission macOS silently drops injected events.
        print(
            "WARNING: no Accessibility permission, so key presses will be ignored by macOS.\n"
            "Add your terminal app in System Settings → Privacy & Security → Accessibility,\n"
            "then quit and reopen the terminal.",
            file=sys.stderr,
            flush=True,
        )
    return PynputOutput()


class ActionDispatcher:
    """Maps trigger actions to outputs. Each trigger enforces its own cooldown."""

    def __init__(
        self,
        output: Output,
        actions: dict[str, str],
        on_fire: Callable[[TriggerEvent, str], None] | None = None,
    ) -> None:
        for action, name in actions.items():
            if name not in OUTPUT_NAMES:
                raise ValueError(
                    f"Action {action!r} maps to unknown output {name!r}; "
                    f"choose from {', '.join(OUTPUT_NAMES)}"
                )
        self._output = output
        self._actions = actions
        self._on_fire = on_fire

    def dispatch(self, event: TriggerEvent) -> bool:
        name = self._actions.get(event.action)
        if name is None:
            print(f"No output configured for action {event.action!r}", file=sys.stderr)
            return False
        self._output.send(name)
        if self._on_fire:
            self._on_fire(event, name)
        return True
