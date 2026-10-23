"""A small modal prompt for one line of text, with OK and Cancel buttons that follow the GUI language."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from eyeokuri.gui.tkutil import place_over
from eyeokuri.i18n import _


def ask_text(parent: tk.Misc, title: str, prompt: str) -> str | None:
    """The text typed, or None if the prompt was canceled. Blocks until it closes."""
    win = tk.Toplevel(parent)
    win.withdraw()
    win.title(title)
    win.resizable(False, False)
    win.transient(parent.winfo_toplevel())
    body = ttk.Frame(win, padding=12)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text=prompt).grid(row=0, column=0, columnspan=2, sticky="w")
    var = tk.StringVar()
    entry = ttk.Entry(body, textvariable=var, width=32)
    entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 12))
    answer: list[str | None] = [None]

    def ok() -> None:
        answer[0] = var.get()
        win.destroy()

    ttk.Button(body, text=_("OK"), style="Accent.TButton", command=ok).grid(row=2, column=0, sticky="e", padx=(0, 6))
    ttk.Button(body, text=_("Cancel"), command=win.destroy).grid(row=2, column=1, sticky="w")
    body.columnconfigure((0, 1), weight=1, uniform="buttons")
    win.bind("<Return>", lambda _e: ok())
    win.bind("<Escape>", lambda _e: win.destroy())
    place_over(win, parent.winfo_toplevel())
    win.grab_set()
    entry.focus_set()
    win.wait_window()
    return answer[0]
