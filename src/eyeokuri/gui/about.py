"""The About window: version, license, and the third-party notices."""

from __future__ import annotations

import os
import sys
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING

from eyeokuri import __version__
from eyeokuri.gui.model import find_notice_file
from eyeokuri.gui.tkutil import place_over
from eyeokuri.i18n import _

if TYPE_CHECKING:
    from eyeokuri.gui.main_window import MainWindow

REPO = "https://github.com/lulalala/eyeokuri"


def _folders() -> list[Path]:
    """Where the license files sit: next to the executable in the Windows build, in the repository root when run from source."""
    if getattr(sys, "frozen", False):
        return [Path(sys.executable).parent]
    return [Path(__file__).resolve().parents[3]]


def _open_file(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)
    else:
        webbrowser.open(path.as_uri())


def _show(name: str) -> None:
    """Opens the shipped copy of a license file, or the repository's copy when it is missing."""
    path = find_notice_file(name, _folders())
    if path is None:
        webbrowser.open(f"{REPO}/blob/master/{name}")
    else:
        _open_file(path)


class AboutWindow:
    def __init__(self, app: MainWindow) -> None:
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.withdraw()
        self.win.title(_("About eyeokuri"))
        self.win.resizable(False, False)
        self.win.transient(app.root)
        body = ttk.Frame(self.win, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=f"eyeokuri {__version__}", font=("TkDefaultFont", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            body,
            text=_("Advance a visual novel with eye and head gestures.") + "\n" + _("Camera frames stay on your PC."),
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 8))
        ttk.Label(
            body,
            text=_("Licensed under the Apache License 2.0. The face model is Google's MediaPipe Face Landmarker, also Apache 2.0."),
            wraplength=360,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 12))
        ttk.Button(body, text=_("License"), command=lambda: _show("LICENSE")).grid(row=3, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(body, text=_("Third-party notices"), command=lambda: _show("THIRD_PARTY_NOTICES.md")).grid(row=3, column=1, sticky="ew")
        body.columnconfigure((0, 1), weight=1, uniform="buttons")
        self.win.bind("<Escape>", lambda _e: self.close())
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        place_over(self.win, app.root)

    def close(self) -> None:
        self.app.about = None
        self.win.destroy()
