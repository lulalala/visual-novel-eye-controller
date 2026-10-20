"""Sending input to the game.

On Windows we call ``SendInput`` with hardware scan codes, which reaches
DirectInput/raw-input games that ignore virtual-key-only events. Elsewhere
(macOS, used for development) we go through pynput.
"""

from __future__ import annotations

import sys
import time
from typing import Callable, Protocol

from eyeokuri.keys import EXTENDED_KEYS, KEY_VK, KeyCombo, parse_key, press_order

MOUSE_OUTPUTS = ("left_click", "right_click", "wheel_down")
# Outputs the app handles itself instead of sending input.
APP_PREFIX = "app:"
APP_OUTPUTS = frozenset({"app:toggle_pause"})
# Common outputs, offered in the gesture window. Any key name or combination
# that parse_key accepts (a, f5, ctrl+s, ...) works too.
OUTPUT_NAMES = ("enter", "space", "left_click", "right_click", "wheel_down", "up", "down", "page_down", "escape")

# Some engines poll key state once per frame, so hold keys down briefly.
_PRESS_DURATION_S = 0.03


def _print_stderr(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


class Output(Protocol):
    def send(self, name: str) -> None: ...


def check_output_name(name: str) -> None:
    """Raises ValueError unless name is a mouse output or a key (combination)."""
    if name not in MOUSE_OUTPUTS:
        parse_key(name)


class Win32Output:
    def __init__(self, log: Callable[[str], None] = _print_stderr) -> None:
        self._log = log
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
        self._user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
        self._user32.MapVirtualKeyW.restype = wintypes.UINT
        self._scans: dict[str, int] = {}

    def send(self, name: str) -> None:
        if name == "left_click":
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
            combo = parse_key(name)
            for key, down in press_order(combo):
                self._key(self._scan(key), up=not down, extended=key in EXTENDED_KEYS)
                if key == combo.key and down:
                    time.sleep(_PRESS_DURATION_S)

    def _scan(self, key: str) -> int:
        # Asks the current layout which key types this letter, so "a" is a on AZERTY too.
        if key not in self._scans:
            self._scans[key] = self._user32.MapVirtualKeyW(KEY_VK[key], 0) & 0xFF  # MAPVK_VK_TO_VSC
        return self._scans[key]

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
            self._log(
                f"SendInput failed (error {err}). If the game runs as administrator, "
                "run eyeokuri as administrator too."
            )


_PYNPUT_NAMES = {"escape": "esc", "win": "cmd"}


class PynputOutput:
    def __init__(self, log: Callable[[str], None] = _print_stderr) -> None:
        self._log = log
        from pynput import keyboard, mouse

        self._keyboard_module = keyboard
        self._keyboard = keyboard.Controller()
        self._mouse = mouse.Controller()
        self._buttons = {"left_click": mouse.Button.left, "right_click": mouse.Button.right}

    def send(self, name: str) -> None:
        if name in self._buttons:
            button = self._buttons[name]
            self._mouse.press(button)
            time.sleep(_PRESS_DURATION_S)
            self._mouse.release(button)
        elif name == "wheel_down":
            self._mouse.scroll(0, -1)
        else:
            self._send_keys(parse_key(name))

    def _send_keys(self, combo: KeyCombo) -> None:
        keys = {k: self._pynput_key(k) for k in (*combo.modifiers, combo.key)}
        missing = [k for k, v in keys.items() if v is None]
        if missing:
            self._log(f"Can't send {combo}: {', '.join(missing)} is not available on this system.")
            return
        for key, down in press_order(combo):
            if down:
                self._keyboard.press(keys[key])
                if key == combo.key:
                    time.sleep(_PRESS_DURATION_S)
            else:
                self._keyboard.release(keys[key])

    def _pynput_key(self, key: str) -> object | None:
        if len(key) == 1:
            return self._keyboard_module.KeyCode.from_char(key)
        # pynput's Key has no f21-f24, and no insert on macOS.
        return getattr(self._keyboard_module.Key, _PYNPUT_NAMES.get(key, key), None)


def macos_accessibility_trusted() -> bool:
    """Whether this process may post input events (System Settings → Accessibility)."""
    import ctypes
    import ctypes.util

    lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("ApplicationServices"))
    lib.AXIsProcessTrusted.restype = ctypes.c_bool
    return bool(lib.AXIsProcessTrusted())


def create_output(log: Callable[[str], None] = _print_stderr) -> Output:
    if sys.platform == "win32":
        return Win32Output(log)
    if sys.platform == "darwin" and not macos_accessibility_trusted():
        # Without this permission macOS silently drops injected events.
        log(
            "WARNING: no Accessibility permission, so key presses will be ignored by macOS.\n"
            "Add your terminal app in System Settings → Privacy & Security → Accessibility,\n"
            "then quit and reopen the terminal."
        )
    return PynputOutput(log)
