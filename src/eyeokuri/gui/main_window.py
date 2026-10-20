"""The main window: the log, with buttons for pause, the camera view, settings and the wizard."""

from __future__ import annotations

import queue
import time
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import messagebox, ttk

from eyeokuri import theme
from eyeokuri.config import Config, GestureConfig, dump_config
from eyeokuri.engine import check_config
from eyeokuri.gui.camera import CameraWindow
from eyeokuri.gui.settings import SettingsWindow
from eyeokuri.gui.wizard import WizardWindow
from eyeokuri.gui.worker import Worker
from eyeokuri.tuning import Take


_POLL_MS = 15


class MainWindow:
    """The log, with buttons for pause, the camera view, settings and the wizard."""

    def __init__(self, root: tk.Tk, config: Config, path: Path) -> None:
        self.root = root
        self.config = config
        self.path = path
        self.settings: SettingsWindow | None = None
        self.wizard: WizardWindow | None = None
        self.camera: CameraWindow | None = None
        self.worker = Worker(config)
        self._shown_status: tuple[str, bool] | None = None

        root.title("eyeokuri")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        bar = ttk.Frame(root, padding=(8, 6))
        bar.grid(row=0, column=0, sticky="ew")
        self.pause_button = ttk.Button(bar, text="Pause", style="Accent.TButton", command=self.worker.toggle_pause)
        self.pause_button.pack(side="left")
        ttk.Button(bar, text="Camera view…", command=self.open_camera).pack(side="left", padx=(6, 0))
        settings_button = ttk.Button(bar, text="Settings…", command=self.open_settings)
        settings_button.pack(side="left", padx=(6, 0))
        wizard_button = ttk.Button(bar, text="Gesture wizard…", command=self.open_wizard)
        wizard_button.pack(side="left", padx=(6, 0))
        # Off while the settings or wizard window is open, which owns the settings in use then.
        self._editing_controls = (self.pause_button, settings_button, wizard_button)

        # The status bar sits at the bottom of the window, with a size grip in its corner.
        status_bar = ttk.Frame(root, padding=(10, 0, 10, 10))
        status_bar.grid(row=3, column=0, sticky="ew")
        self.status = ttk.Label(status_bar, text="Starting…", foreground=theme.MUTED)
        self.status.pack(side="left")
        ttk.Sizegrip(status_bar).pack(side="right", anchor="se")

        side = ttk.Frame(root)
        side.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        side.columnconfigure(0, weight=1)
        side.rowconfigure(0, weight=1)
        self.log_text = tk.Text(side, width=90, height=24, wrap="word", state="disabled", font="TkFixedFont",
                                borderwidth=0, padx=8, pady=6, highlightthickness=1,
                                highlightbackground=theme.LINE, highlightcolor=theme.LINE)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(side, orient="vertical", command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.tag_configure("fire", foreground=theme.OK)
        self.log_text.tag_configure("reject", foreground=theme.MUTED)
        self.log_text.tag_configure("time", foreground=theme.MUTED)

        root.bind("p", lambda _e: self._editing or self.worker.toggle_pause())
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._poll()

    def _poll(self) -> None:
        for _ in range(200):
            try:
                self._append_log(self.worker.logs.get_nowait())
            except queue.Empty:
                break
        status = self.worker.status
        if status is not None and status != self._shown_status:
            self._shown_status = status
            text, paused = status
            self.status.configure(text=text, foreground=theme.ACCENT if paused else theme.MUTED)
            self.pause_button.configure(text="Resume" if paused else "Pause")
        if self.camera is not None:
            self.camera.show(self.worker.frame)
        self.root.after(_POLL_MS, self._poll)

    def _append_log(self, message: str) -> None:
        if " -> " in message and "not sent" not in message:
            tag = "fire"
        elif message.endswith(")") and "(" in message:
            tag = "reject"
        else:
            tag = ""
        at_end = self.log_text.yview()[1] > 0.999
        self.log_text.configure(state="normal")
        self.log_text.insert("end", time.strftime("%H:%M:%S  "), "time")
        self.log_text.insert("end", message + "\n", tag)
        self.log_text.configure(state="disabled")
        if at_end:
            self.log_text.see("end")

    def apply_config(self, config: Config) -> None:
        self.config = config
        self.push_config()

    @property
    def _editing(self) -> bool:
        return self.settings is not None or self.wizard is not None

    def push_config(self) -> None:
        """Sends the settings in use to the engine. Gestures are off while the settings
        or wizard window is open, so editing and recording send nothing to other windows."""
        self.worker.set_config(self.config)
        self.worker.set_suspended(self._editing)
        for button in self._editing_controls:
            button.configure(state="disabled" if self._editing else "normal")

    def save_config(self, config: Config) -> None:
        self.apply_config(config)
        self.path.write_text(dump_config(config), encoding="utf-8")

    def open_camera(self) -> None:
        if self.camera is not None:
            self.camera.win.lift()
            self.camera.win.focus_force()
            return
        self.camera = CameraWindow(self)

    def open_settings(self) -> None:
        if self.settings is not None:
            self.settings.win.lift()
            self.settings.win.focus_force()
            return
        self.settings = SettingsWindow(self)
        self.push_config()

    def open_wizard(self, settings: SettingsWindow | None = None) -> None:
        """From the settings window, the wizard starts from its edits and hands
        the result back to it; otherwise it uses and applies the settings in use."""
        if self.wizard is not None:
            self.wizard.win.lift()
            return
        name = settings.current if settings is not None else next(iter(self.config.gestures))
        self.wizard = WizardWindow(self, settings, name)
        self.push_config()

    def use_fit(self, name: str, gesture: GestureConfig, takes: list[Take]) -> None:
        """Applies the wizard's result and offers to save."""
        config = replace(self.config, gestures={**self.config.gestures, name: gesture})
        check_config(config)
        self.apply_config(config)
        self.worker.log(f"{name}: wizard settings applied")
        if messagebox.askyesno("Gesture wizard", f"{name} is using the new settings.\n\n"
                               f"Save them to {self.path}?", parent=self.root):
            try:
                self.save_config(config)
                self.worker.log(f"Saved to {self.path}")
            except OSError as e:
                messagebox.showerror("Gesture wizard", f"Couldn't save {self.path}:\n\n{e}", parent=self.root)

    def close(self) -> None:
        self.worker.stop()
        self.root.destroy()
