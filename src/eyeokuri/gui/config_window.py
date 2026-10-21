"""The config window: camera, feedback and the eye and head baseline settings."""

from __future__ import annotations

import tkinter as tk
from dataclasses import fields, replace
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Any

from eyeokuri import theme
from eyeokuri.config import Config
from eyeokuri.engine import check_config
from eyeokuri.gui.camera import CameraPicker
from eyeokuri.gui.model import fmt
from eyeokuri.gui.tkutil import place_over

if TYPE_CHECKING:
    from eyeokuri.gui.main_window import MainWindow


# Edits apply once they stop for this long, so typing "12" doesn't open camera 1 first.
_APPLY_DELAY_MS = 400
# Settings that stay in the config file but not on the General tab. They only
# decide which frames the eye baseline learns from, not when a gesture fires.
_HIDDEN_GENERAL = {("eyes", "close_ratio"), ("eyes", "open_ratio")}
# Settings sections on the General tab, and on the Advanced tab for the baseline settings.
_GENERAL_SECTIONS = ("camera", "feedback")
_ADVANCED_SECTIONS = ("eyes", "head")
# One-line help beside each General field, in user terms.
_GENERAL_HELP = {
    ("camera", "index"): "Which camera to use. 0 is usually the built-in one.",
    ("camera", "width"): "Frame width in pixels (at least 160).",
    ("camera", "height"): "Frame height in pixels (at least 120).",
    ("camera", "fps"): "Frames per second to ask the camera for.",
    ("eyes", "baseline_window_s"): "Seconds of history used to learn your usual open-eye level. "
                                   "Try 5 if lighting or distance changes quickly.",
    ("eyes", "warmup_s"): "Seconds to learn before blinks can trigger. Must be below the window.",
    ("eyes", "require_both_eyes"): "Both eyes must close, so a wink doesn't count.",
    ("head", "baseline_window_s"): "Seconds of history used to learn your usual head position. "
                                   "Raise it if looking away for a while shifts your zero.",
    ("head", "warmup_s"): "Seconds to learn before head gestures can trigger. Must be below the window.",
    ("feedback", "sound"): "Play a sound when a gesture fires or you pause.",
    ("feedback", "log_rejected"): "Log gestures that were detected but didn't fire, and why.",
}
_SECTIONS = (*_GENERAL_SECTIONS, *_ADVANCED_SECTIONS)


class ConfigWindow:
    """General and Advanced settings. Edits apply live; OK saves, Cancel goes back."""

    def __init__(self, app: MainWindow) -> None:
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.withdraw()
        self.win.title("eyeokuri config")
        self.win.protocol("WM_DELETE_WINDOW", self._close_box)
        self._field_errors: dict[str, str] = {}
        self.camera_picker: CameraPicker | None = None
        # Cancel goes back to these.
        self._opened_with = app.config
        self._apply_id: str | None = None
        self.values = {
            section: {f.name: getattr(getattr(app.config, section), f.name) for f in fields(getattr(app.config, section))}
            for section in _SECTIONS
        }

        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(0, weight=1)
        notebook = ttk.Notebook(self.win)
        notebook.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        general_tab = ttk.Frame(notebook, padding=12)
        advanced_tab = ttk.Frame(notebook, padding=12)
        notebook.add(general_tab, text="General")
        notebook.add(advanced_tab, text="Advanced")
        self.vars: list[Any] = []
        self._build_tab(general_tab, _GENERAL_SECTIONS, "Changing camera settings reopens the camera.")
        self._build_tab(advanced_tab, _ADVANCED_SECTIONS, (
            "Most people never need to change these. Changing them makes eyeokuri learn your usual "
            "eye openness and head position again."))

        bottom = ttk.Frame(self.win, padding=(8, 0, 8, 8))
        bottom.grid(row=1, column=0, sticky="ew")
        self.message = ttk.Label(bottom, text="", foreground=theme.BAD, wraplength=640)
        self.message.pack(side="left", fill="x", expand=True)
        ttk.Button(bottom, text="Cancel", command=self.cancel).pack(side="right")
        self.ok_button = ttk.Button(bottom, text="OK", style="Accent.TButton", command=self.ok)
        self.ok_button.pack(side="right", padx=6)
        place_over(self.win, app.root)

    def build_config(self) -> Config:
        """The settings in use with these edits; raises ValueError if they aren't valid."""
        if self._field_errors:
            raise ValueError(next(iter(self._field_errors.values())))
        base = self.app.config
        config = replace(base, **{s: replace(getattr(base, s), **v) for s, v in self.values.items()})
        check_config(config)
        return config

    def _build_tab(self, tab: ttk.Frame, sections: tuple[str, ...], note: str) -> None:
        ttk.Label(tab, foreground=theme.MUTED, wraplength=640, justify="left", text=note).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        row = 1
        for section in sections:
            values = self.values[section]
            ttk.Label(tab, text=section.capitalize(), font="TkHeadingFont").grid(
                row=row, column=0, sticky="w", pady=(8, 2))
            row += 1
            for key, value in values.items():
                if (section, key) in _HIDDEN_GENERAL:
                    continue
                ttk.Label(tab, text=key).grid(row=row, column=0, sticky="w", padx=(12, 8))
                if isinstance(value, bool):
                    bvar = tk.BooleanVar(value=value)
                    ttk.Checkbutton(tab, variable=bvar, command=lambda s=section, k=key, v=bvar: self._on_bool(
                        s, k, v.get())).grid(row=row, column=1, sticky="w")
                    self.vars.append(bvar)
                else:
                    svar = tk.StringVar(value=fmt(value) if isinstance(value, float) else str(value))
                    svar.trace_add("write", lambda *_a, s=section, k=key, v=svar, t=type(value): self._on_text(
                        s, k, v.get(), t))
                    ttk.Entry(tab, textvariable=svar, width=10).grid(row=row, column=1, sticky="w")
                    self.vars.append(svar)
                help_text = _GENERAL_HELP.get((section, key))
                if (section, key) == ("camera", "index"):
                    # The button and its help share one cell so the help sits right next to the button.
                    cell = ttk.Frame(tab)
                    cell.grid(row=row, column=2, sticky="w")
                    ttk.Button(cell, text="Choose from live views…",
                               command=lambda v=svar: self._pick_camera(v)).grid(row=0, column=0, sticky="w")
                    if help_text:
                        ttk.Label(cell, text=help_text, foreground=theme.MUTED, wraplength=380, justify="left").grid(
                            row=0, column=1, sticky="w", padx=(8, 0))
                elif help_text:
                    ttk.Label(tab, text=help_text, foreground=theme.MUTED, wraplength=380, justify="left").grid(
                        row=row, column=2, sticky="w", padx=(8, 0))
                row += 1

    def _pick_camera(self, var: tk.StringVar) -> None:
        if self.camera_picker is not None and self.camera_picker.win.winfo_exists():
            self.camera_picker.win.lift()
            return
        # The view shown for "in use" is the running camera, not necessarily the edited index.
        running = self.app.config.camera.index
        self.camera_picker = CameraPicker(self.win, self.app, running, lambda i: var.set(str(i)))

    def _on_bool(self, section: str, key: str, value: bool) -> None:
        self.values[section][key] = value
        self._refresh()

    def _on_text(self, section: str, key: str, text: str, kind: type) -> None:
        label = f"{section}.{key}"
        try:
            self.values[section][key] = kind(text.strip())
            self._field_errors.pop(label, None)
        except ValueError:
            self._field_errors[label] = f"{label}: {text!r} is not a{'n integer' if kind is int else ' number'}"
        self._refresh()

    def _refresh(self) -> None:
        """Validates the edits, then applies them once they stop changing."""
        if self._apply_id is not None:
            self.win.after_cancel(self._apply_id)
            self._apply_id = None
        try:
            self.build_config()
            self.message.configure(text="")
            self.ok_button.configure(state="normal")
            self._apply_id = self.win.after(_APPLY_DELAY_MS, self._apply)
        except ValueError as e:
            self.message.configure(text=str(e), foreground=theme.BAD)
            self.ok_button.configure(state="disabled")

    def _apply(self) -> None:
        """Puts valid edits in use; invalid ones wait until you fix them."""
        if self._apply_id is not None:
            self.win.after_cancel(self._apply_id)
            self._apply_id = None
        try:
            config = self.build_config()
        except ValueError:
            return
        if config != self.app.config:
            self.app.apply_config(config)

    def ok(self) -> None:
        """Saves and closes; if saving fails, the window stays open with your edits."""
        try:
            config = self.build_config()
            self.app.save_config(config)
        except (ValueError, OSError) as e:
            self.message.configure(text=str(e), foreground=theme.BAD)
            return
        self._close()

    def cancel(self) -> None:
        """Goes back to the settings in use when the window opened, and closes."""
        if self.app.config != self._opened_with:
            self.app.apply_config(self._opened_with)
        self._close()

    def _close_box(self) -> None:
        """The window's close button cancels, but asks first so one click can't undo your changes."""
        try:
            changed = self.build_config() != self._opened_with
        except ValueError:
            changed = True
        if changed and not messagebox.askyesno(
                "eyeokuri config", "Discard your changes?", icon="warning", parent=self.win):
            return
        self.cancel()

    def _close(self) -> None:
        if self._apply_id is not None:
            self.win.after_cancel(self._apply_id)
        if self.camera_picker is not None and self.camera_picker.win.winfo_exists():
            self.camera_picker.close()
        self.app.config_window = None
        self.app.push_config()
        self.win.destroy()
