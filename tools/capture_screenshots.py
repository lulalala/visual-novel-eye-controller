"""Takes the site's GUI screenshots from the real windows, in any GUI language.

    .venv\\Scripts\\python tools\\capture_screenshots.py --language zh-TW

The windows run on a scripted source (a blink, a head shake, steady eyes), so no
camera is used and no camera image appears in the screenshots. Nothing is sent
to other windows and no sound plays. The config is saved in a temporary folder.

Windows only. It copies the pixels from the screen, so leave the mouse and other
windows alone while it runs (about 40 seconds). The result depends on your display
scaling and Windows theme; use the same ones each time so the screenshots match.
"""

from __future__ import annotations

import argparse
import ctypes
import math
import sys
import tempfile
import threading
import time
import tkinter as tk
from collections import deque
from ctypes import wintypes
from dataclasses import replace
from functools import partial
from pathlib import Path

import cv2
import numpy as np

from eyeokuri import i18n, theme
from eyeokuri.config import Config
from eyeokuri.engine import Engine
from eyeokuri.gui import worker as worker_module
from eyeokuri.gui.main_window import MainWindow
from eyeokuri.sources import EYE_OPENNESS, HEAD_POSE, Signals

FPS = 30
OPEN = 0.30
"""The scripted eye openness when open. Any scale works: gestures use the ratio to the open level."""

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "site" / "src" / "assets" / "screenshots"
NAMES = ("main-window", "gesture-window", "wizard-take", "config-general")


# Frames: (eye openness as a ratio of OPEN, head yaw in degrees). One frame is 1/FPS seconds.

Frames = list[tuple[float, float]]


def steady(seconds: float) -> Frames:
    return [(1.0, 0.0)] * round(seconds * FPS)


def blink(closed_frames: int = 10) -> Frames:
    """Eyes closing, staying closed for closed_frames, and opening again."""
    return [(0.5, 0.0)] + [(0.15, 0.0)] * closed_frames + [(0.5, 0.0), (1.0, 0.0)]


def shake() -> Frames:
    """Turn about 24° to one side, then to the other, in half a second."""
    yaws = [8, 16, 24, 24, 16, 8, 0, -8, -16, -24, -24, -16, -8, 0]
    return [(1.0, float(y)) for y in yaws]


class ScriptedSource:
    """A Source that plays queued frames in real time and holds steady open eyes when the queue is empty."""

    name = "scripted"
    provides = frozenset({EYE_OPENNESS, HEAD_POSE})

    def __init__(self) -> None:
        self._queue: deque[tuple[float, float] | None] = deque()
        self._lock = threading.Lock()
        self._frame = 0
        self._next = time.monotonic()
        self._release = threading.Event()
        self.frozen = threading.Event()
        """Set while read() waits at a freeze() mark."""

    def play(self, frames: Frames) -> None:
        with self._lock:
            self._queue.extend(frames)

    def freeze(self) -> None:
        """Holds the source after the queued frames, until release(). The windows then see a still signal."""
        with self._lock:
            self._queue.append(None)
        self._release.clear()
        self.frozen.clear()

    def release(self) -> None:
        self._release.set()

    @property
    def idle(self) -> bool:
        with self._lock:
            return not self._queue

    def read(self) -> Signals:
        with self._lock:
            item = self._queue.popleft() if self._queue else (1.0, 0.0)
        if item is None:
            self.frozen.set()
            self._release.wait()
            self._next = time.monotonic()
            return self.read()
        ratio, yaw = item
        self._next += 1 / FPS
        time.sleep(max(0.0, self._next - time.monotonic()))
        self._frame += 1
        # A small wobble, so the plot's line isn't a ruler.
        wobble = 1 + 0.025 * math.sin(self._frame * 1.1)
        value = OPEN * ratio * (wobble if ratio == 1.0 else 1.0)
        return Signals(time.monotonic(), True, (value, value), head_yaw_deg=yaw, head_pitch_deg=0.0)

    def debug_view(self) -> np.ndarray | None:
        return None

    def close(self) -> None:
        self.release()


class SilentOutput:
    def send(self, name: str) -> None:
        pass


# Screen capture


def _frame_rect(win: tk.Misc) -> tuple[int, int, int, int]:
    """Left, top, right and bottom of the window's visible frame, title bar included."""
    rect = wintypes.RECT()
    # DWMWA_EXTENDED_FRAME_BOUNDS leaves out the invisible resize margin.
    ctypes.windll.dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(int(win.wm_frame(), 16)), 9, ctypes.byref(rect), ctypes.sizeof(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def grab(left: int, top: int, right: int, bottom: int) -> np.ndarray:
    """The screen's pixels in this rectangle, as a BGR image."""
    width, height = right - left, bottom - top
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    handle = ctypes.c_void_p
    user32.GetDC.restype = handle
    user32.GetDC.argtypes = [handle]
    user32.ReleaseDC.argtypes = [handle, handle]
    gdi32.CreateCompatibleDC.restype = handle
    gdi32.CreateCompatibleDC.argtypes = [handle]
    gdi32.CreateCompatibleBitmap.restype = handle
    gdi32.CreateCompatibleBitmap.argtypes = [handle, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.restype = handle
    gdi32.SelectObject.argtypes = [handle, handle]
    gdi32.BitBlt.argtypes = [handle, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             handle, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
    gdi32.GetDIBits.argtypes = [handle, handle, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                                ctypes.c_void_p, wintypes.UINT]
    gdi32.DeleteObject.argtypes = [handle]
    gdi32.DeleteDC.argtypes = [handle]

    class BitmapInfo(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("width", wintypes.LONG), ("height", wintypes.LONG),
                    ("planes", wintypes.WORD), ("bits", wintypes.WORD), ("compression", wintypes.DWORD),
                    ("image_size", wintypes.DWORD), ("x_ppm", wintypes.LONG), ("y_ppm", wintypes.LONG),
                    ("used", wintypes.DWORD), ("important", wintypes.DWORD)]

    info = BitmapInfo(size=ctypes.sizeof(BitmapInfo), width=width, height=-height, planes=1, bits=32)
    screen = user32.GetDC(None)
    memory = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
    gdi32.SelectObject(memory, bitmap)
    gdi32.BitBlt(memory, 0, 0, width, height, screen, left, top, 0x00CC0020)  # SRCCOPY
    pixels = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(memory, bitmap, 0, height, pixels, ctypes.byref(info), 0)  # DIB_RGB_COLORS
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memory)
    user32.ReleaseDC(None, screen)
    return np.frombuffer(pixels, np.uint8).reshape(height, width, 4)[:, :, :3].copy()


class Session:
    def __init__(self, root: tk.Tk, out: Path, only: set[str]) -> None:
        self.root = root
        self.out = out
        self.only = only
        self.saved: list[Path] = []

    def pump(self, seconds: float) -> None:
        """Lets the windows run (and redraw) for this long."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.01)

    def pump_until(self, done, timeout: float = 20.0) -> None:
        end = time.monotonic() + timeout
        while not done():
            if time.monotonic() > end:
                raise TimeoutError("the scripted source did not finish")
            self.pump(0.02)

    def shoot(self, name: str, win: tk.Misc) -> None:
        """Saves the window, title bar included, as <name>.png."""
        if name not in self.only:
            return
        win.attributes("-topmost", True)
        win.lift()
        win.focus_force()
        self.pump(0.5)
        image = grab(*_frame_rect(win))
        win.attributes("-topmost", False)
        ok, png = cv2.imencode(".png", image)
        assert ok
        path = self.out / f"{name}.png"
        path.write_bytes(png.tobytes())
        self.saved.append(path)


def run(language: str, out: Path, only: set[str]) -> list[Path]:
    if sys.platform != "win32":
        raise SystemExit("This script captures Windows windows; run it on Windows.")
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # like the app, so the pixels are sharp
    except (AttributeError, OSError):
        pass
    i18n.set_language(language)
    out.mkdir(parents=True, exist_ok=True)
    source = ScriptedSource()
    # The worker builds its own Engine; give it the scripted source, no output and no sound.
    worker_module.Engine = partial(Engine, source=source, output=SilentOutput(), sound=lambda _name: None)
    root = tk.Tk()
    theme.apply(root)
    root.geometry("+40+40")
    session = Session(root, out, only)
    with tempfile.TemporaryDirectory() as folder:
        main = MainWindow(root, replace(Config(), app=replace(Config().app, paused=False)), Path(folder) / "config.toml")
        try:
            _scenes(session, main, source)
        finally:
            source.release()
            main.close()
    return session.saved


def _scenes(s: Session, main: MainWindow, source: ScriptedSource) -> None:
    # Let the eye and head trackers learn the steady pose.
    s.pump(3.5)

    # Main window: a quick blink that is turned down, two blinks that fire, then a head shake to pause and another to resume.
    source.play(blink(2) + steady(0.8) + blink() + steady(0.8) + blink() + steady(0.8)
                + shake() + steady(1.5) + shake() + steady(1.5))
    s.pump_until(lambda: source.idle)
    s.pump(0.5)
    s.shoot("main-window", main.root)

    # Gesture window: the plot shows 4 seconds, a blink 1.4 s in, then the source holds still.
    main.open_gesture("blink")
    gesture = main.gesture_window
    assert gesture is not None
    source.play(steady(1.4) + blink() + steady(4.0 - 1.4 - 12 / FPS))
    source.freeze()
    s.pump_until(source.frozen.is_set)
    s.pump(0.8)
    s.shoot("gesture-window", gesture.win)

    # Wizard: the first take, one blink recorded.
    source.release()
    s.pump(0.5)
    main.open_wizard(gesture)
    wizard = main.wizard
    assert wizard is not None
    s.pump(0.5)
    wizard._toggle_record()  # what the Record button and Space do
    source.play(steady(0.5) + blink() + steady(1.0))
    s.pump_until(lambda: source.idle)
    wizard._toggle_record()
    s.pump(0.8)
    s.shoot("wizard-take", wizard.win)
    wizard.close()
    gesture.cancel()
    s.pump(0.3)

    # Config window, General tab.
    main.open_config()
    config = main.config_window
    assert config is not None
    s.pump(0.5)
    s.shoot("config-general", config.win)
    config.cancel()


def main() -> int:
    p = argparse.ArgumentParser(description="Take the site's GUI screenshots from the real windows.")
    p.add_argument("--language", default="en", help='GUI language: "en" or a catalog code such as zh-TW (default: en)')
    p.add_argument("--out", type=Path, help="folder to save into (default: site/src/assets/screenshots, "
                   "plus /<language in lowercase> for languages other than en)")
    p.add_argument("--only", help=f"comma-separated names to save, from: {', '.join(NAMES)} (default: all)")
    args = p.parse_args()
    only = set(args.only.split(",")) if args.only else set(NAMES)
    if only - set(NAMES):
        p.error(f"unknown name(s): {', '.join(sorted(only - set(NAMES)))}")
    out = args.out or (SHOTS if args.language == "en" else SHOTS / args.language.lower())
    for path in run(args.language, out, only):
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
