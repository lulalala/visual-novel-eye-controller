"""Tk helpers: window placement and fonts."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import font as tkfont


def place_over(win: tk.Toplevel, anchor: tk.Misc) -> None:
    """Shows a withdrawn window centered over the anchor window, moved as
    little as needed to fit on the anchor's screen.

    A window taller than the anchor lines up with its top instead."""
    win.update_idletasks()
    top = anchor.winfo_toplevel()
    # The anchor's border and title bar; the new window gets the same ones.
    border = max(0, top.winfo_rootx() - top.winfo_x())
    title = max(0, top.winfo_rooty() - top.winfo_y())
    width = win.winfo_reqwidth() + 2 * border
    height = win.winfo_reqheight() + title + border
    anchor_width = top.winfo_width() + 2 * border
    anchor_height = top.winfo_height() + title + border
    x = top.winfo_x() + (anchor_width - width) // 2
    y = top.winfo_y() + max(0, (anchor_height - height) // 2)
    left, upper, right, lower = _work_area(top)
    # When the window is bigger than the screen, its top left corner stays visible.
    x = max(left, min(x, right - width))
    y = max(upper, min(y, lower - height))
    win.geometry(f"+{x}+{y}")
    win.deiconify()


def _work_area(win: tk.Misc) -> tuple[int, int, int, int]:
    """The left, top, right and bottom of the usable part (without the
    taskbar) of the screen the window is on."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class MonitorInfo(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        try:
            user32 = ctypes.windll.user32
            user32.MonitorFromWindow.restype = wintypes.HMONITOR
            user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
            user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MonitorInfo)]
            hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
            monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
            info = MonitorInfo(cbSize=ctypes.sizeof(MonitorInfo))
            if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                work = info.rcWork
                return work.left, work.top, work.right, work.bottom
        except (AttributeError, OSError):
            pass
    return 0, 0, win.winfo_screenwidth(), win.winfo_screenheight()


def scaled_font(name: str, by: float) -> tkfont.Font:
    font = tkfont.nametofont(name).copy()
    font.configure(size=round(font.cget("size") * by))
    return font
