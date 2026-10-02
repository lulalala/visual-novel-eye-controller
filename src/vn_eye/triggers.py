"""Gesture triggers. Each trigger turns a stream of observations into actions.

To add a gesture (e.g. dwell on a screen zone), implement ``Trigger`` and
register it in ``create_triggers``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from vn_eye.config import Config, LongBlinkConfig
from vn_eye.eyes import EyeObservation


@dataclass(frozen=True)
class TriggerEvent:
    trigger: str
    action: str
    timestamp: float
    detail: str = ""


class Trigger(Protocol):
    name: str

    def update(self, obs: EyeObservation) -> TriggerEvent | None: ...

    def reset(self) -> None: ...

    def status(self) -> str:
        """Short human-readable state for the preview window."""
        ...


class LongBlinkTrigger:
    """Fires when both eyes stay closed for a deliberate length of time."""

    name = "long_blink"

    def __init__(self, config: LongBlinkConfig, log: Callable[[str], None] | None = None) -> None:
        if config.fire_on not in ("reopen", "hold"):
            raise ValueError(f"long_blink.fire_on must be 'reopen' or 'hold', not {config.fire_on!r}")
        self.config = config
        self._log = log or (lambda _msg: None)
        self._closed_since: float | None = None
        self._fired = False
        self._last_duration = 0.0

    def reset(self) -> None:
        self._closed_since = None
        self._fired = False

    def update(self, obs: EyeObservation) -> TriggerEvent | None:
        if not obs.face_present or not obs.ready:
            # Losing the face mid-closure (turning away, leaning out) cancels it.
            if self._closed_since is not None and not self._fired:
                self._log(f"{self.name}: closure cancelled (face lost)")
            self.reset()
            return None

        t = obs.timestamp
        if obs.closed:
            if self._closed_since is None:
                self._closed_since = t
                self._fired = False
            duration = t - self._closed_since
            self._last_duration = duration
            if (
                self.config.fire_on == "hold"
                and not self._fired
                and duration >= self.config.min_duration_s
            ):
                self._fired = True
                return self._event(t, duration)
            return None

        if self._closed_since is None:
            return None
        duration = t - self._closed_since
        self._last_duration = duration
        self._closed_since = None
        if self._fired:  # "hold" mode already fired during this closure
            return None
        if duration < self.config.min_duration_s:
            self._log(
                f"{self.name}: blink {duration:.2f}s (too short, min {self.config.min_duration_s:.2f}s)"
            )
            return None
        if self.config.fire_on == "reopen" and duration > self.config.max_duration_s:
            self._log(
                f"{self.name}: closed {duration:.2f}s "
                f"(too long, cancelled; max {self.config.max_duration_s:.2f}s)"
            )
            return None
        if self.config.fire_on == "reopen":
            return self._event(t, duration)
        return None

    def status(self) -> str:
        if self._closed_since is not None:
            return f"closed {self._last_duration:.2f}s"
        return f"open (last closure {self._last_duration:.2f}s)"

    def _event(self, t: float, duration: float) -> TriggerEvent:
        return TriggerEvent(self.name, self.config.action, t, f"closed {duration:.2f}s")


def create_triggers(config: Config, log: Callable[[str], None] | None = None) -> list[Trigger]:
    triggers: list[Trigger] = []
    if config.long_blink.enabled:
        triggers.append(LongBlinkTrigger(config.long_blink, log))
    return triggers
