"""Audible confirmation that a trigger fired, played without blocking."""

from __future__ import annotations

import subprocess
import sys
import threading


def _play() -> None:
    try:
        if sys.platform == "win32":
            import winsound

            winsound.Beep(880, 60)
        elif sys.platform == "darwin":
            subprocess.run(["afplay", "/System/Library/Sounds/Tink.aiff"], check=False)
        else:
            sys.stdout.write("\a")
            sys.stdout.flush()
    except Exception:
        pass


def play_trigger_sound() -> None:
    threading.Thread(target=_play, daemon=True).start()
