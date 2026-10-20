"""The main window: the gesture list with on/off toggles, and the log."""

from __future__ import annotations

import queue
import time
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from eyeokuri import theme
from eyeokuri.config import Config, GestureConfig, StepConfig, dump_config
from eyeokuri.engine import check_config
from eyeokuri.gui.camera import CameraWindow
from eyeokuri.gui.config_window import ConfigWindow
from eyeokuri.gui.gesture_window import GestureWindow
from eyeokuri.gui.model import GESTURE_NAME
from eyeokuri.gui.wizard import WizardWindow
from eyeokuri.gui.worker import Worker


_POLL_MS = 15


class MainWindow:
    """The gesture list (each with its key, an on/off toggle and Configure…),
    a toggle for all gestures (pause), and the log."""

    def __init__(self, root: tk.Tk, config: Config, path: Path) -> None:
        self.root = root
        self.config = config
        self.path = path
        self.gesture_window: GestureWindow | None = None
        self.config_window: ConfigWindow | None = None
        self.wizard: WizardWindow | None = None
        self.camera: CameraWindow | None = None
        self.worker = Worker(config)
        self._shown_status: tuple[str, bool] | None = None
        self._shown_rows: tuple[tuple[str, str, bool], ...] | None = None
        self._row_controls: list[ttk.Widget] = []

        root.title("eyeokuri")
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        menubar = tk.Menu(root)
        self.file_menu = tk.Menu(menubar, tearoff=False)
        self.file_menu.add_command(label="Config…", command=self.open_config)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Quit", command=self.close)
        menubar.add_cascade(label="File", menu=self.file_menu)
        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(label="Camera view…", command=self.open_camera)
        menubar.add_cascade(label="View", menu=view_menu)
        root.configure(menu=menubar)

        left = ttk.Frame(root, padding=(8, 8, 0, 8))
        left.grid(row=0, column=0, sticky="ns")
        self.rows = ttk.Frame(left)
        self.rows.pack(anchor="nw")
        self.running = tk.BooleanVar(value=not config.app.paused)
        self.new_button = ttk.Button(left, text="New gesture…", command=self.new_gesture)
        self.new_button.pack(anchor="w", pady=(10, 0))
        self._build_rows()

        side = ttk.Frame(root)
        side.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        side.columnconfigure(0, weight=1)
        side.rowconfigure(0, weight=1)
        self.log_text = tk.Text(side, width=70, height=24, wrap="word", state="disabled", font="TkFixedFont",
                                borderwidth=0, padx=8, pady=6, highlightthickness=1,
                                highlightbackground=theme.LINE, highlightcolor=theme.LINE)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(side, orient="vertical", command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.tag_configure("fire", foreground=theme.OK)
        self.log_text.tag_configure("reject", foreground=theme.MUTED)
        self.log_text.tag_configure("time", foreground=theme.MUTED)

        # The status bar sits at the bottom of the window, with a size grip in its corner.
        status_bar = ttk.Frame(root, padding=(10, 0, 10, 10))
        status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.status = ttk.Label(status_bar, text="Starting…", foreground=theme.MUTED)
        self.status.pack(side="left")
        ttk.Sizegrip(status_bar).pack(side="right", anchor="se")

        root.bind("p", lambda _e: self._editing or self.worker.toggle_pause())
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._poll()

    # Gesture list

    def _build_rows(self) -> None:
        """One row per gesture, under a row that turns all of them on or off (pause)."""
        self._shown_rows = tuple((n, g.output, g.enabled) for n, g in self.config.gestures.items())
        for child in self.rows.winfo_children():
            child.destroy()
        for col, text in enumerate(("Gesture", "Key", "On")):
            ttk.Label(self.rows, text=text, foreground=theme.MUTED).grid(row=0, column=col, sticky="w", padx=4)
        ttk.Label(self.rows, text="All gestures", font="TkHeadingFont").grid(row=1, column=0, sticky="w", padx=4)
        pause_toggle = ttk.Checkbutton(self.rows, variable=self.running, command=self._toggle_pause)
        pause_toggle.grid(row=1, column=2, padx=4, pady=2)
        ttk.Separator(self.rows).grid(row=2, column=0, columnspan=4, sticky="ew", pady=4)
        self._row_controls = [pause_toggle]
        for r, (name, gesture) in enumerate(self.config.gestures.items(), 3):
            ttk.Label(self.rows, text=name).grid(row=r, column=0, sticky="w", padx=4)
            ttk.Label(self.rows, text=gesture.output or "(none)",
                      foreground=theme.INK if gesture.output else theme.MUTED).grid(row=r, column=1, sticky="w", padx=4)
            var = tk.BooleanVar(value=gesture.enabled)
            toggle = ttk.Checkbutton(self.rows, variable=var, command=lambda n=name, v=var: self._set_enabled(n, v))
            toggle.grid(row=r, column=2, padx=4, pady=2)
            configure = ttk.Button(self.rows, text="Configure…", command=lambda n=name: self.open_gesture(n))
            configure.grid(row=r, column=3, padx=4, pady=2)
            # Tk drops a variable nobody refers to, and its checkbox goes blank.
            toggle.var = var  # type: ignore[attr-defined]
            self._row_controls += [toggle, configure]
        self._set_controls()

    def _set_enabled(self, name: str, var: tk.BooleanVar) -> None:
        """Turns one gesture on or off, and saves."""
        gestures, enabled = self.config.gestures, var.get()
        config = replace(self.config, gestures={**gestures, name: replace(gestures[name], enabled=enabled)})
        try:
            check_config(config)
            self.save_config(config)
        except (ValueError, OSError) as e:
            var.set(not enabled)
            messagebox.showerror("eyeokuri", f"Couldn't turn {name} {'on' if enabled else 'off'}:\n\n{e}",
                                 parent=self.root)
            return
        self.worker.log(f"{name}: {'on' if enabled else 'off'}")

    def _toggle_pause(self) -> None:
        # The checkbox follows the engine in _poll, which also saves the change.
        self.running.set(not self.config.app.paused)
        self.worker.toggle_pause()

    def _save_paused(self, paused: bool) -> None:
        """Saves pause, whichever way it changed (the toggle, p or a gesture), so the next start matches."""
        config = replace(self.config, app=replace(self.config.app, paused=paused))
        try:
            self.save_config(config)
        except OSError as e:
            self.worker.log(f"Couldn't save {self.path}: {e}")

    def new_gesture(self) -> None:
        name = simpledialog.askstring("New gesture", "Name (letters, digits, _ and -):", parent=self.root)
        if not name:
            return
        if not GESTURE_NAME.fullmatch(name) or name in self.config.gestures:
            messagebox.showerror("New gesture", f"{name!r} is taken or has other characters than "
                                 "letters, digits, _ and -.", parent=self.root)
            return
        self.gesture_window = GestureWindow(self, name, GestureConfig(steps=[StepConfig(signal="eyes", below_ratio=0.55)]))
        self.push_config()

    # Polling

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
            self.running.set(not paused)
        # While a window has unsaved edits in use, saving now would save those too; it waits until they close.
        if status is not None and status[1] != self.config.app.paused and not self._editing:
            self._save_paused(status[1])
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

    # Settings

    def apply_config(self, config: Config) -> None:
        self.config = config
        self.push_config()
        if tuple((n, g.output, g.enabled) for n, g in config.gestures.items()) != self._shown_rows:
            self._build_rows()

    @property
    def _editing(self) -> bool:
        return self.gesture_window is not None or self.config_window is not None or self.wizard is not None

    def push_config(self) -> None:
        """Sends the settings in use to the engine. Gestures are off while a gesture,
        config or wizard window is open, so editing and recording send nothing to other windows."""
        self.worker.set_config(self.config)
        self.worker.set_suspended(self._editing)
        self._set_controls()

    def _set_controls(self) -> None:
        # Off while another window is open, which owns the settings in use then.
        state = "disabled" if self._editing else "normal"
        for widget in [*self._row_controls, self.new_button]:
            widget.configure(state=state)
        self.file_menu.entryconfigure("Config…", state=state)

    def save_config(self, config: Config) -> None:
        self.apply_config(config)
        self.path.write_text(dump_config(config), encoding="utf-8")

    # Windows

    def open_camera(self) -> None:
        if self.camera is not None:
            self.camera.win.lift()
            self.camera.win.focus_force()
            return
        self.camera = CameraWindow(self)

    def open_gesture(self, name: str) -> None:
        if self.gesture_window is not None:
            self.gesture_window.win.lift()
            self.gesture_window.win.focus_force()
            return
        self.gesture_window = GestureWindow(self, name)
        self.push_config()

    def open_config(self) -> None:
        if self.config_window is not None:
            self.config_window.win.lift()
            self.config_window.win.focus_force()
            return
        self.config_window = ConfigWindow(self)
        self.push_config()

    def open_wizard(self, owner: GestureWindow) -> None:
        """The wizard starts from the gesture window's edits and hands the result back to it."""
        if self.wizard is not None:
            self.wizard.win.lift()
            return
        self.wizard = WizardWindow(self, owner)
        self.push_config()

    def close(self) -> None:
        self.worker.stop()
        self.root.destroy()
