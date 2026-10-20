"""Tk helpers: window placement and size, and fonts."""

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


def place_beside(win: tk.Toplevel, anchor: tk.Misc, gap: int = 8) -> None:
    """Shows a withdrawn window next to the anchor window, tops lined up:
    on its right, or on its left when the right has no room. When neither
    side has room, it goes on the roomier side, as close as fits on the screen."""
    win.update_idletasks()
    top = anchor.winfo_toplevel()
    left, upper, right, lower = _frame(top)
    # The new window gets the anchor's border and title bar, but no menu bar.
    width = win.winfo_reqwidth() + (right - left) - top.winfo_width()
    height = win.winfo_reqheight() + (lower - upper) - top.winfo_height() - menu_bar_height(top)
    area_left, area_top, area_right, area_bottom = _work_area(top)
    if right + gap + width <= area_right:
        x = right + gap
    elif left - gap - width >= area_left:
        x = left - gap - width
    elif area_right - right >= left - area_left:
        x = right + gap
    else:
        x = left - gap - width
    x = max(area_left, min(x, area_right - width))
    y = max(area_top, min(upper, area_bottom - height))
    # Tk places the outer frame, which on Windows has an invisible margin around the visible one.
    win.geometry(f"+{x - (left - top.winfo_x())}+{y - (upper - top.winfo_y())}")
    win.deiconify()


def menu_bar_height(win: tk.Misc) -> int:
    """The height of the window's menu bar, which Tk leaves out of the window's height."""
    top = win.winfo_toplevel()
    menu = top.cget("menu")
    if not menu or sys.platform == "darwin":
        # macOS shows the menu at the top of the screen instead.
        return 0
    if sys.platform == "win32":
        import ctypes

        try:
            return int(ctypes.windll.user32.GetSystemMetrics(15))  # SM_CYMENU
        except (AttributeError, OSError):
            return 0
    return top.nametowidget(menu).winfo_reqheight()


def _frame(win: tk.Misc) -> tuple[int, int, int, int]:
    """The left, top, right and bottom of the window's visible frame, title bar included."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        try:
            rect = wintypes.RECT()
            # DWMWA_EXTENDED_FRAME_BOUNDS leaves out the invisible resize margin.
            if ctypes.windll.dwmapi.DwmGetWindowAttribute(
                    wintypes.HWND(int(win.wm_frame(), 16)), 9, ctypes.byref(rect), ctypes.sizeof(rect)) == 0:
                return rect.left, rect.top, rect.right, rect.bottom
        except (AttributeError, OSError, ValueError):
            pass
    border = max(0, win.winfo_rootx() - win.winfo_x())
    return (win.winfo_x(), win.winfo_y(),
            win.winfo_rootx() + win.winfo_width() + border, win.winfo_rooty() + win.winfo_height() + border)


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
