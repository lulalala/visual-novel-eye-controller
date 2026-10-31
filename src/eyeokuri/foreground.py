"""Which program's window is in front, so the GUI can use that program's config.

The executable name and window title stay in memory; programs.py writes them
to a file only when you create a config for that program."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Seen:
    """The foreground window."""

    exe: str
    """The executable's file name (``CLANNAD.exe``), or "" if Windows won't tell."""
    title: str
    own: bool = False
    """The window is one of eyeokuri's."""
    shell: bool = False
    """The taskbar, Alt+Tab, the Start menu or the desktop: what you pass through to switch programs."""


# Window classes of the Windows shell.
_SHELL_CLASSES = frozenset({
    "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW", "MultitaskingViewFrame",
    "TaskSwitcherWnd", "XamlExplorerHostIslandWindow", "ForegroundStaging", "Windows.UI.Core.CoreWindow",
})


class ForegroundProbe:
    """Reads the foreground window. On other platforms than Windows, read() is always None."""

    def __init__(self) -> None:
        self._hwnd: int | None = None
        self._seen: Seen | None = None
        self._win = sys.platform == "win32"
        if not self._win:
            return
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        self._wintypes = wintypes
        self._user32 = ctypes.WinDLL("user32")
        self._kernel32 = ctypes.WinDLL("kernel32")
        self._user32.GetForegroundWindow.restype = wintypes.HWND
        self._user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        self._user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        self._user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        self._kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        self._kernel32.OpenProcess.restype = wintypes.HANDLE
        self._kernel32.QueryFullProcessImageNameW.argtypes = (
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
        self._kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

    def read(self) -> Seen | None:
        """The foreground window, or None when no window is in front."""
        if not self._win:
            return None
        hwnd = self._user32.GetForegroundWindow()
        if not hwnd:
            return None
        # The executable only changes with the window, so it's looked up once per window.
        if hwnd != self._hwnd:
            self._hwnd = hwnd
            self._seen = self._describe(hwnd)
        return self._seen

    def _describe(self, hwnd: int) -> Seen:
        ctypes, wintypes = self._ctypes, self._wintypes
        pid = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        title = ctypes.create_unicode_buffer(512)
        self._user32.GetWindowTextW(hwnd, title, len(title))
        cls = ctypes.create_unicode_buffer(256)
        self._user32.GetClassNameW(hwnd, cls, len(cls))
        return Seen(exe=self._exe_name(pid.value), title=title.value,
                    own=pid.value == os.getpid(), shell=cls.value in _SHELL_CLASSES)

    def _exe_name(self, pid: int) -> str:
        ctypes, wintypes = self._ctypes, self._wintypes
        handle = self._kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(len(buf))
            if not self._kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return ""
            return buf.value.replace("/", "\\").rsplit("\\", 1)[-1]
        finally:
            self._kernel32.CloseHandle(handle)
