"""Audible feedback, played without blocking."""

from __future__ import annotations

import subprocess
import sys
import threading

# kind -> (Windows beep frequency Hz, duration ms, macOS system sound)
_SOUNDS = {
    "trigger": (880, 60, "Tink"),
    "pause": (440, 150, "Bottle"),
    "resume": (660, 150, "Pop"),
}


def _play(kind: str) -> None:
    freq, ms, mac_sound = _SOUNDS[kind]
    try:
        if sys.platform == "win32":
            import winsound

            winsound.Beep(freq, ms)
        elif sys.platform == "darwin":
            subprocess.run(["afplay", f"/System/Library/Sounds/{mac_sound}.aiff"], check=False)
        else:
            sys.stdout.write("\a")
            sys.stdout.flush()
    except Exception:
        pass


def play_sound(kind: str = "trigger") -> None:
    threading.Thread(target=_play, args=(kind,), daemon=True).start()
