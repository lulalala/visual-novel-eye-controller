"""What the gesture, key and config windows share: edits apply live, OK saves, Cancel goes back."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Callable

from eyeokuri import theme
from eyeokuri.config import Config
from eyeokuri.engine import check_config
from eyeokuri.i18n import _

if TYPE_CHECKING:
    from eyeokuri.gui.main_window import MainWindow


# Edits apply once they stop for this long, so typing "12" doesn't apply 1 (or open camera 1) first.
APPLY_DELAY_MS = 400


class LiveEdit:
    """An editor window's settings: the ones in use when it opened, and the edits.

    Valid edits go in use once they stop changing; invalid ones wait until
    you fix them, with the reason in ``message`` and ``ok_button`` off.
    ``edited`` builds the settings with the window's edits."""

    def __init__(self, app: MainWindow, win: tk.Toplevel, message: ttk.Label, ok_button: ttk.Button,
                 edited: Callable[[], Config]) -> None:
        self.app = app
        self.win = win
        self.message = message
        self.ok_button = ok_button
        self._edited = edited
        self.opened_with = app.config
        """Cancel goes back to these."""
        self.errors: dict[str, str] = {}
        """Fields whose text isn't a value yet, by label, with what's wrong."""
        self._apply_id: str | None = None

    def config(self) -> Config:
        """The settings in use with these edits; raises ValueError if they aren't valid."""
        if self.errors:
            raise ValueError(next(iter(self.errors.values())))
        config = self._edited()
        check_config(config)
        return config

    def refresh(self) -> Config | None:
        """Validates the edits and shows the result, then applies them once they
        stop changing. Returns the settings, or None if they aren't valid."""
        self._cancel_apply()
        try:
            config = self.config()
        except ValueError as e:
            self.show_error(str(e))
            self.ok_button.configure(state="disabled")
            return None
        self.message.configure(text="")
        self.ok_button.configure(state="normal")
        self._apply_id = self.win.after(APPLY_DELAY_MS, self.apply)
        return config

    def apply(self) -> None:
        """Puts valid edits in use; invalid ones wait until you fix them."""
        self._cancel_apply()
        try:
            config = self.config()
        except ValueError:
            return
        if config != self.app.config:
            self.app.apply_config(config)

    def save(self) -> Config | None:
        """Saves the edits. If they aren't valid or can't be written, shows why and returns None."""
        try:
            config = self.config()
            self.app.save_config(config)
        except (ValueError, OSError) as e:
            self.show_error(str(e))
            return None
        return config

    def revert(self) -> None:
        """Goes back to the settings in use when the window opened."""
        if self.app.config != self.opened_with:
            self.app.apply_config(self.opened_with)

    def may_discard(self, title: str, changed: bool = False) -> bool:
        """Whether closing may drop the edits: when there are none (and not
        ``changed``), or you agree, so one click can't undo your changes."""
        try:
            changed = changed or self.config() != self.opened_with
        except ValueError:
            changed = True
        return not changed or messagebox.askyesno(title, _("Discard your changes?"), icon="warning", parent=self.win)

    def show_error(self, text: str) -> None:
        self.message.configure(text=text, foreground=theme.BAD)

    def close(self) -> None:
        self._cancel_apply()

    def _cancel_apply(self) -> None:
        if self._apply_id is not None:
            self.win.after_cancel(self._apply_id)
            self._apply_id = None
