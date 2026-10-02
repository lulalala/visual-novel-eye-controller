"""Global pause/resume hotkey, so blinks can't fire while you do something else."""

from __future__ import annotations

import sys
import threading
from typing import Callable


class PauseSwitch:
    def __init__(self, on_change: Callable[[bool], None] | None = None) -> None:
        self._paused = threading.Event()
        self._listener = None
        self._on_change = on_change

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    def toggle(self) -> None:
        if self._paused.is_set():
            self._paused.clear()
            print("Resumed", flush=True)
        else:
            self._paused.set()
            print("Paused", flush=True)
        if self._on_change:
            self._on_change(self.paused)

    def start_global_hotkey(self, combo: str) -> None:
        if not combo:
            return
        try:
            from pynput import keyboard

            self._listener = keyboard.GlobalHotKeys({combo: self.toggle})
            self._listener.start()
            print(f"Pause hotkey: {combo}", flush=True)
        except Exception as e:  # e.g. missing Input Monitoring permission on macOS
            print(f"Global hotkey unavailable ({e}); use 'p' in the preview window.", file=sys.stderr)

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
