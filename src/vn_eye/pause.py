"""Pause switch, so gestures don't send input while you do something else."""

from __future__ import annotations

from typing import Callable


class PauseSwitch:
    def __init__(self, on_change: Callable[[bool], None] | None = None) -> None:
        self.paused = False
        self._on_change = on_change

    def toggle(self) -> None:
        self.paused = not self.paused
        print("Paused" if self.paused else "Resumed", flush=True)
        if self._on_change:
            self._on_change(self.paused)
