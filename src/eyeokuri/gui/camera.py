"""The live camera view window and the camera chooser."""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Callable

from eyeokuri import theme
from eyeokuri.gui.model import view_size
from eyeokuri.gui.tkutil import place_beside
from eyeokuri.sources.camera import CameraScanner

if TYPE_CHECKING:
    from eyeokuri.gui.main_window import MainWindow


class CameraWindow:
    """The live camera view. The worker only draws it while this window is open."""

    def __init__(self, app: MainWindow) -> None:
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.withdraw()
        self.win.title("eyeokuri camera view")
        self.win.resizable(False, False)
        width, height = view_size(app.config.camera)
        self.photo = tk.PhotoImage(width=width, height=height)
        # No padding, so the window is as tall as the main window (see MainWindow).
        ttk.Label(self.win, image=self.photo, anchor="center", padding=0, borderwidth=0).pack(fill="both", expand=True)
        self.win.bind("p", lambda _e: app.worker.toggle_pause())
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self._shown: bytes | None = None
        app.worker.show_view.set()
        place_beside(self.win, app.root)

    def show(self, frame: bytes | None) -> None:
        if frame is not None and frame is not self._shown:
            self._shown = frame
            self.photo.configure(data=frame, format="ppm")

    def close(self) -> None:
        self.app.worker.show_view.clear()
        self.app.worker.frame = None
        self.app.camera = None
        self.win.destroy()


class CameraPicker:
    """Lists every camera with its live view; clicking one chooses it.

    The running camera can't be opened twice, so its tile shows the main
    window's own view."""

    def __init__(self, parent: tk.Misc, app: MainWindow, current: int, choose: Callable[[int], None]) -> None:
        self.app = app
        self.current = current
        self.choose = choose
        self.win = tk.Toplevel(parent)
        self.win.title("Choose a camera")
        self.win.transient(parent)  # type: ignore[arg-type]
        self.status = ttk.Label(self.win, text="Looking for cameras…", foreground=theme.MUTED)
        self.status.pack(anchor="w", padx=10, pady=(8, 0))
        self.grid = ttk.Frame(self.win, padding=8)
        self.grid.pack(fill="both", expand=True)
        self.tiles: dict[int, tuple[ttk.Label, tk.PhotoImage | None]] = {}
        self._shown: dict[int, bytes] = {}
        self._was_viewing = app.worker.show_view.is_set()
        app.worker.show_view.set()
        self.scanner = CameraScanner(skip=current)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self._poll()

    def _poll(self) -> None:
        if not self.win.winfo_exists():
            return
        frames = self.scanner.frames()
        if self.app.worker.frame is not None:
            # Same frame the main window shows, so it stays valid for the other camera's size.
            tmp = tk.PhotoImage(data=self.app.worker.frame, format="ppm")
            if tmp.width() > 320:
                tmp = tmp.subsample(math.ceil(tmp.width() / 320))
            frames[self.current] = tmp  # type: ignore[assignment]
        for index in sorted(frames):
            data = frames[index]
            if index not in self.tiles:
                self._add_tile(index)
            label, _ = self.tiles[index]
            if isinstance(data, bytes):
                if self._shown.get(index) is data:
                    continue
                self._shown[index] = data
                photo = tk.PhotoImage(data=data, format="ppm")
            else:
                photo = data
            label.configure(image=photo)
            self.tiles[index] = (label, photo)  # keep a reference or Tk drops the image
        if self.scanner.scanning:
            self.status.configure(text="Looking for cameras…")
        elif not self.tiles:
            self.status.configure(text="No cameras found.")
        else:
            self.status.configure(text="Click a camera to use it.")
        self.win.after(100, self._poll)

    def _add_tile(self, index: int) -> None:
        tile = ttk.Frame(self.grid, padding=4, relief="solid")
        n = len(self.tiles)
        tile.grid(row=n // 2, column=n % 2, padx=4, pady=4)
        label = ttk.Label(tile, cursor="hand2")
        label.pack()
        caption = f"Camera {index}" + (" (in use)" if index == self.current else "")
        ttk.Button(tile, text=f"Use {caption.lower()}" if index != self.current else caption,
                   command=lambda: self._pick(index)).pack(fill="x", pady=(4, 0))
        label.bind("<Button-1>", lambda _e: self._pick(index))
        self.tiles[index] = (label, None)

    def _pick(self, index: int) -> None:
        self.choose(index)
        self.close()

    def close(self) -> None:
        self.scanner.close()
        if not self._was_viewing:
            self.app.worker.show_view.clear()
            self.app.worker.frame = None
        self.win.destroy()
