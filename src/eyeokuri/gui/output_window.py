"""The key window: what one gesture sends, and whether it presses or holds it."""

from __future__ import annotations

import sys
import tkinter as tk
from dataclasses import replace
from tkinter import ttk
from typing import TYPE_CHECKING

from eyeokuri import theme
from eyeokuri.config import Config
from eyeokuri.gui.live_edit import LiveEdit
from eyeokuri.gui.tkutil import id_box, place_over
from eyeokuri.i18n import _
from eyeokuri.keys import from_tk_event, lone_modifier_from_tk
from eyeokuri.labels import show_gesture, show_output_mode
from eyeokuri.outputs import APP_OUTPUTS, OUTPUT_MODES, OUTPUT_NAMES

if TYPE_CHECKING:
    from eyeokuri.gui.main_window import MainWindow


class OutputWindow:
    """Edits one gesture's output and output mode. Edits apply live; OK saves, Cancel goes back."""

    def __init__(self, app: MainWindow, name: str) -> None:
        self.app = app
        self.name = name
        gesture = app.config.gestures[name]
        self.output = gesture.output
        self.output_mode = gesture.output_mode

        self.win = tk.Toplevel(app.root)
        self.win.withdraw()
        self.title = show_gesture(name) + " – " + _("Key")
        self.win.title(self.title)
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self._close_box)
        body = ttk.Frame(self.win, padding=12)
        body.grid(row=0, column=0, sticky="nsew")
        self._build(body)

        bottom = ttk.Frame(self.win, padding=(12, 0, 12, 12))
        bottom.grid(row=1, column=0, sticky="ew")
        self.message = ttk.Label(bottom, text="", foreground=theme.BAD, wraplength=360)
        self.message.pack(side="top", anchor="w", pady=(0, 6))
        ttk.Button(bottom, text=_("Cancel"), command=self.cancel).pack(side="right")
        self.ok_button = ttk.Button(bottom, text=_("OK"), style="Accent.TButton", command=self.ok)
        self.ok_button.pack(side="right", padx=6)
        self.edit = LiveEdit(app, self.win, self.message, self.ok_button, self._edited)
        place_over(self.win, app.root)
        self._refresh()

    def _edited(self) -> Config:
        """The settings in use with this gesture's new output."""
        base = self.app.config
        gesture = replace(base.gestures[self.name], output=self.output, output_mode=self.output_mode)
        return replace(base, gestures={**base.gestures, self.name: gesture})

    def _build(self, body: ttk.Frame) -> None:
        ttk.Label(body, text=_("Key")).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=2)
        # Editable: any key or combination (f5, ctrl+s) can be typed, or captured with the button.
        self.output_var = tk.StringVar(value=self.output or "(none)")
        self.output_var.trace_add("write", lambda *_a: self._on_output())
        ttk.Combobox(body, width=18, textvariable=self.output_var,
                     values=["(none)", *OUTPUT_NAMES, *sorted(APP_OUTPUTS)]).grid(row=0, column=1, sticky="ew", pady=2)
        self.capture_button = ttk.Button(body, text=_("Press a key…"), command=self._toggle_capture)
        self.capture_button.grid(row=0, column=2, sticky="w", padx=(4, 0), pady=2)
        self._capturing = False

        ttk.Label(body, text=_("Send")).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=2)
        id_box(body, list(OUTPUT_MODES), show_output_mode, self.output_mode, self._on_output_mode,
               min_width=18).grid(row=1, column=1, sticky="ew", pady=2)
        ttk.Label(body, foreground=theme.MUTED, wraplength=360, justify="left", text=_(
            "Press once sends the key each time the gesture fires. Hold while it lasts holds the key "
            "down until the gesture ends.")).grid(row=2, column=1, columnspan=2, sticky="w", pady=(4, 0))

    def _on_output(self) -> None:
        output = self.output_var.get().strip().lower()
        # Invalid text is stored too; LiveEdit reports it, and nothing applies until it's fixed.
        self.output = "" if output in ("", "(none)") else output
        self._refresh()

    def _on_output_mode(self, mode: str) -> None:
        self.output_mode = mode
        self._refresh()

    def _refresh(self) -> None:
        """Validates the edits, then applies them once they stop changing."""
        self.edit.refresh()

    # Key capture

    def _toggle_capture(self) -> None:
        if self._capturing:
            self._stop_capture()
            return
        self._capturing = True
        self.capture_button.configure(text=_("Press a key now (click to cancel)"))
        # Keys go to the focused button; "break" stops Space or Tab from acting on it.
        self.capture_button.focus_set()
        self.capture_button.bind("<KeyPress>", self._on_capture_key)
        self.capture_button.bind("<KeyRelease>", self._on_capture_release)
        self.capture_button.bind("<FocusOut>", lambda _e: self._stop_capture())
        # The modifier pressed last, while no other key has been pressed after it.
        self._lone_modifier: str | None = None

    def _on_capture_key(self, event: tk.Event) -> str:
        name = from_tk_event(event.keysym, event.state, sys.platform)
        if name is not None:
            self._stop_capture()
            self.output_var.set(name)
        else:
            self._lone_modifier = lone_modifier_from_tk(event.keysym)
        return "break"

    def _on_capture_release(self, event: tk.Event) -> str:
        # A modifier released with no key pressed after it is the key itself (ctrl to skip text).
        name = lone_modifier_from_tk(event.keysym)
        if name is not None and name == self._lone_modifier:
            self._stop_capture()
            self.output_var.set(name)
        return "break"

    def _stop_capture(self) -> None:
        if not self._capturing:
            return
        self._capturing = False
        self.capture_button.unbind("<KeyPress>")
        self.capture_button.unbind("<KeyRelease>")
        self.capture_button.unbind("<FocusOut>")
        self.capture_button.configure(text=_("Press a key…"))

    # Buttons

    def ok(self) -> None:
        """Saves and closes; if saving fails, the window stays open with your edits."""
        if self.edit.save() is not None:
            self._close()

    def cancel(self) -> None:
        """Goes back to the settings in use when the window opened, and closes."""
        self.edit.revert()
        self._close()

    def _close_box(self) -> None:
        """The window's close button cancels, but asks first so one click can't undo your changes."""
        if self.edit.may_discard(self.title):
            self.cancel()

    def _close(self) -> None:
        self._stop_capture()
        self.edit.close()
        self.app.output_window = None
        self.app.push_config()
        self.win.destroy()
