"""Runs the engine on a background thread for the GUI."""

from __future__ import annotations

import queue
import threading
from collections import deque
from dataclasses import replace

import cv2

from eyeokuri import preview
from eyeokuri.config import Config
from eyeokuri.engine import Engine
from eyeokuri.eyes import Observation
from eyeokuri.i18n import _
from eyeokuri.gui.model import VIEW_MAX_WIDTH


_HISTORY_FRAMES = 900
# A wizard take stops by itself after this long; the history keeps a bit more.
MAX_TAKE_S = 20.0


def state_text(obs: Observation, paused: bool, suspended: bool, fps: float) -> str:
    if suspended:
        state = _("Gestures off while editing")
    elif paused:
        state = _("Paused")
    elif not obs.face_present:
        state = _("No face")
    elif not obs.ready:
        state = _("Calibrating…")
    else:
        state = _("Eyes closed") if obs.closed else _("Watching")
    return f"{state}   {fps:4.1f} fps"


class Worker:
    """Runs the engine on a background thread. Only the main thread touches
    Tk widgets; it picks up frames and log lines from here."""

    def __init__(self, config: Config) -> None:
        self.logs: queue.Queue[str] = queue.Queue()
        self.status: tuple[str, bool] | None = None
        """The latest (status text, paused). Replaced each frame, never queued."""
        self.frame: bytes | None = None
        """The latest camera view as a PPM image, while show_view is set."""
        self.show_view = threading.Event()
        self.engine: Engine | None = None
        self._config = config
        self._suspended = False
        self._history: deque[Observation] = deque(maxlen=_HISTORY_FRAMES)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def log(self, message: str) -> None:
        self.logs.put(message)

    def _run(self) -> None:
        self.log("Starting the camera…")
        config = self._config
        try:
            engine = Engine(config, self.log)
        except Exception as e:  # noqa: BLE001 - shown to the user instead of a traceback
            self.log(f"Couldn't start: {e}")
            return
        with self._lock:
            self.engine = engine
            # The camera takes a few seconds to start; settings changed
            # meanwhile must not be lost.
            if self._config is not config:
                engine.set_config(self._config)
            engine.set_suspended(self._suspended)
        self.log("Running. Keep your eyes open normally for a couple of seconds to calibrate.")
        try:
            while not self._stop.is_set():
                frame = engine.step()
                obs = frame.obs
                with self._lock:
                    self._history.append(obs)
                self.status = (state_text(obs, engine.paused, engine.suspended, engine.fps), engine.paused)
                if not self.show_view.is_set():
                    # Drawing and converting the view costs CPU on every frame.
                    continue
                assert engine.config is not None
                img = preview.render(
                    engine.source.debug_view(), obs, engine.config.eyes, engine.statuses(),
                    engine.paused, engine.fps, obs.timestamp - engine.last_fire_at < preview.FLASH_S,
                    hints=False,
                )
                if img.shape[1] > VIEW_MAX_WIDTH:
                    scale = VIEW_MAX_WIDTH / img.shape[1]
                    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                self.frame = b"P6 %d %d 255\n" % (rgb.shape[1], rgb.shape[0]) + rgb.tobytes()
        except Exception as e:  # noqa: BLE001
            self.log(f"Stopped: {e}")
        finally:
            engine.close()

    def set_config(self, config: Config) -> None:
        with self._lock:
            self._config = config
            if self.engine is not None:
                self.engine.set_config(config)

    def set_suspended(self, suspended: bool) -> None:
        with self._lock:
            self._suspended = suspended
            if self.engine is not None:
                self.engine.set_suspended(suspended)

    def toggle_pause(self) -> None:
        if self.engine is not None:
            self.engine.toggle_pause()

    def recent(self, seconds: float) -> list[Observation]:
        """The last ``seconds`` of observations, with time starting at 0."""
        with self._lock:
            history = list(self._history)
        if not history:
            return []
        start = max(history[-1].timestamp - seconds, history[0].timestamp)
        return [replace(o, timestamp=o.timestamp - start) for o in history if o.timestamp >= start]

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)
