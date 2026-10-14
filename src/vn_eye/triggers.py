"""Gestures. Each gesture matches a sequence of states (or other gestures) in the observations.

A state is where the eyes or head are: eyes closed, head turned left, head
back at center. A gesture's steps count the moment you reach each state, so
a blink is "eyes_closed, then eyes_open".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from vn_eye.config import STATES, Config, GestureConfig
from vn_eye.eyes import Observation
from vn_eye.sources import EYE_OPENNESS, HEAD_POSE, Source


@dataclass(frozen=True)
class TriggerEvent:
    trigger: str
    action: str
    timestamp: float
    detail: str = ""


class Trigger(Protocol):
    name: str
    needs: frozenset[str]
    """Signals the source must provide (see vn_eye.sources); otherwise the trigger is skipped."""

    def update(self, obs: Observation) -> TriggerEvent | None: ...

    def reset(self) -> None: ...

    def status(self) -> str:
        """Short human-readable state for the preview window."""
        ...


# Head axes: the states on each side. Positive pitch = head tilted down;
# positive yaw = face turned toward the camera image's right, which is your left.
_AXES = {
    "pitch": ("head_down", "head_up"),
    "yaw": ("head_left", "head_right"),
}


class StateTracker:
    """Reports the states that the eyes, or the head on one axis, arrive at."""

    def __init__(self, signal: str, config: GestureConfig) -> None:
        self.signal = signal
        self._config = config
        self._state: str | None = None
        self._since = 0.0
        self._value: float | None = None

    def reset(self) -> None:
        # The next frame sets the state again without counting as an arrival.
        self._state = None

    def update(self, obs: Observation) -> tuple[bool, list[str]]:
        """Returns (signal available, states reached this frame)."""
        state = self._read(obs)
        if state is None:
            self.reset()
            return False, []
        previous = self._state
        if state == previous:
            return True, []
        self._state = state
        self._since = obs.timestamp
        if previous is None:
            return True, []
        if previous not in ("head_center", "eyes_open", "eyes_closed") and state != "head_center":
            # Swinging straight from one side to the other passes through center.
            return True, ["head_center", state]
        return True, [state]

    def _read(self, obs: Observation) -> str | None:
        if self.signal == "eyes":
            # Eye states share [eyes] close_ratio/open_ratio, which also decide
            # which samples the open-eye baseline learns from.
            if not obs.face_present or not obs.ready:
                return None
            return "eyes_closed" if obs.closed else "eyes_open"
        value = obs.head_pitch if self.signal == "pitch" else obs.head_yaw
        self._value = value
        if not obs.face_present or value is None:
            return None
        positive, negative = _AXES[self.signal]
        cfg = self._config
        # Staying on a side only needs release_deg; reaching one needs past_deg.
        if value > (cfg.release_deg if self._state == positive else cfg.past_deg):
            return positive
        if -value > (cfg.release_deg if self._state == negative else cfg.past_deg):
            return negative
        return "head_center"

    def status(self, now: float) -> str:
        if self.signal == "eyes":
            if self._state == "eyes_closed":
                return f"closed {now - self._since:.2f}s"
            return "open" if self._state else "no eyes"
        return f"no {self.signal}" if self._value is None else f"{self.signal} {self._value:+.0f}°"


@dataclass(frozen=True)
class _Partial:
    """Steps matched so far: what is left, the first step's time, and the last step."""

    remaining: tuple[str, ...]
    start: float
    last_step: str
    last_time: float


class GestureTrigger:
    """Fires when its steps happen in order, each within the allowed gap of the one before."""

    def __init__(
        self,
        name: str,
        config: GestureConfig,
        log: Callable[[str], None] | None = None,
        gestures: dict[str, GestureTrigger] | None = None,
    ) -> None:
        _validate(name, config)
        gestures = gestures or {}
        self.name = name
        self.config = config
        self._log = log or (lambda _msg: None)
        self._steps = tuple(config.steps)
        self._trackers = [StateTracker(s, config) for s in _signals(self._steps)]
        self._gestures = [gestures[s] for s in dict.fromkeys(self._steps) if s not in STATES]
        needs = {EYE_OPENNESS if t.signal == "eyes" else HEAD_POSE for t in self._trackers}
        for gesture in self._gestures:
            needs |= gesture.needs
        self.needs = frozenset(needs)
        self._partials: list[_Partial] = []
        self._last_fire: float | None = None
        self._now = 0.0
        self.fired = False
        """True on the frame this gesture fires, for gestures that use it as a step."""

    def reset(self) -> None:
        for tracker in self._trackers:
            tracker.reset()
        self._partials = []

    def update(self, obs: Observation) -> TriggerEvent | None:
        self.fired = False
        t = self._now = obs.timestamp
        arrived: list[str] = []
        lost = not obs.face_present
        for tracker in self._trackers:
            available, states = tracker.update(obs)
            lost = lost or not available
            arrived += states
        cfg = self.config
        if cfg.within_s:
            # Much older starts aren't attempts at this gesture, so they expire quietly.
            self._partials = [p for p in self._partials if t - p.start <= 2 * cfg.within_s]
        if lost:
            # Losing the face (or the signal) mid-gesture cancels it.
            if self._partials:
                self._log(f"{self.name}: canceled (face lost)")
            self.reset()
            return None
        arrived += [g.name for g in self._gestures if g.fired]
        for step in arrived:
            event = self._step(step, t)
            if event is not None:
                return event
        return None

    def _step(self, step: str, t: float) -> TriggerEvent | None:
        cfg = self.config
        advanced: list[_Partial] = []
        kept: list[_Partial] = []
        for p in self._partials:
            i = _next_index(p.remaining, step, cfg.any_order)
            if i is None:
                kept.append(p)
                continue
            gap = t - p.last_time
            reason = None
            if cfg.gap_min_s and gap < cfg.gap_min_s:
                reason = f"too short, min {cfg.gap_min_s:.2f}s"
            elif cfg.gap_max_s and gap > cfg.gap_max_s:
                reason = f"too long, max {cfg.gap_max_s:.2f}s"
            if reason:
                # A failed step ends this attempt; the next first step starts a new one.
                self._log(f"{self.name}: {p.last_step} to {step} in {gap:.2f}s ({reason})")
                continue
            advanced.append(_Partial(p.remaining[:i] + p.remaining[i + 1 :], p.start, step, t))
        i = _next_index(self._steps, step, cfg.any_order)
        if i is not None:
            advanced.append(_Partial(self._steps[:i] + self._steps[i + 1 :], t, step, t))

        # Keep one partial per remaining state: when a step repeats, the newer one wins.
        latest: dict[tuple[str, ...], _Partial] = {}
        for p in [*kept, *advanced]:
            if p.remaining and (p.remaining not in latest or p.start > latest[p.remaining].start):
                latest[p.remaining] = p
        self._partials = list(latest.values())
        done = [p for p in advanced if not p.remaining]
        if not done:
            return None

        match = max(done, key=lambda p: p.start)
        took = t - match.start
        if len(self._steps) == 1:
            detail = step
        else:
            detail = f"{self._steps[0]} to {step} in {took:.2f}s"
        if cfg.within_s and took > cfg.within_s:
            self._log(f"{self.name}: {detail} (too slow, max {cfg.within_s:.2f}s)")
            return None
        if self._last_fire is not None and t - self._last_fire < cfg.cooldown_s:
            self._log(f"{self.name}: {detail} (cooldown {cfg.cooldown_s:.2f}s)")
            return None
        self._last_fire = t
        # The step that completed this match can't start the next one.
        self._partials = []
        self.fired = True
        return TriggerEvent(self.name, self.name, t, detail)

    def status(self) -> str:
        parts = [tracker.status(self._now) for tracker in self._trackers]
        if len(self._steps) > 1 and self._partials:
            matched = len(self._steps) - min(len(p.remaining) for p in self._partials)
            parts.append(f"{matched}/{len(self._steps)} steps")
        return ", ".join(parts) or "waiting"


def _signals(steps: tuple[str, ...]) -> list[str]:
    """The signals to track. head_center counts on the axes the gesture turns
    or tilts on, so a nod isn't completed by the head turning back to center."""
    signals: list[str] = []
    if any(s in ("eyes_closed", "eyes_open") for s in steps):
        signals.append("eyes")
    for axis, sides in _AXES.items():
        if any(s in sides for s in steps):
            signals.append(axis)
    if "head_center" in steps and not any(s in _AXES for s in signals):
        signals += list(_AXES)
    return signals


def _next_index(remaining: tuple[str, ...], step: str, any_order: bool) -> int | None:
    if any_order:
        return remaining.index(step) if step in remaining else None
    return 0 if remaining[0] == step else None


def _validate(name: str, config: GestureConfig) -> None:
    key = f"gestures.{name}"
    if not config.steps or not all(isinstance(s, str) for s in config.steps):
        raise ValueError(f"{key}.steps must list at least one state or gesture name")
    for field_name in ("gap_min_s", "gap_max_s", "within_s", "cooldown_s"):
        value = getattr(config, field_name)
        if value < 0:
            raise ValueError(f"{key}.{field_name} must be 0 or more, not {value}")
    if config.gap_max_s and config.gap_max_s < config.gap_min_s:
        raise ValueError(
            f"{key}.gap_max_s must be 0 (no limit) or at least {key}.gap_min_s "
            f"({config.gap_min_s}), not {config.gap_max_s}"
        )
    if any(s.startswith("head_") for s in config.steps) and not (
        0 <= config.release_deg < config.past_deg
    ):
        # With release_deg >= past_deg, the head would leave a side on the frame it got there.
        raise ValueError(
            f"{key}.release_deg must be at least 0 and below {key}.past_deg "
            f"({config.past_deg}), not {config.release_deg}"
        )


def create_triggers(config: Config, log: Callable[[str], None] | None = None) -> list[Trigger]:
    """Builds the enabled gestures, each one after the gestures it uses as steps."""
    gestures = config.gestures
    built: dict[str, GestureTrigger] = {}

    def build(name: str, chain: tuple[str, ...]) -> None:
        if name in built:
            return
        if name in chain:
            loop = " -> ".join((*chain[chain.index(name) :], name))
            raise ValueError(f"gestures.{name}.steps: gestures refer to each other in a loop ({loop})")
        cfg = gestures[name]
        for step in cfg.steps:
            if step in STATES:
                continue
            if step not in gestures:
                raise ValueError(
                    f"gestures.{name}.steps: unknown step {step!r}; use a state "
                    f"({', '.join(STATES)}) or another gesture's name"
                )
            if not gestures[step].enabled:
                raise ValueError(
                    f"gestures.{name}.steps: {step} is disabled (gestures.{step}.enabled = false)"
                )
            build(step, (*chain, name))
        built[name] = GestureTrigger(name, cfg, log, built)

    for name, cfg in gestures.items():
        if cfg.enabled:
            build(name, ())
    return list(built.values())


def supported_triggers(
    triggers: list[Trigger], source: Source, log: Callable[[str], None]
) -> list[Trigger]:
    """Keeps the triggers whose needed signals the source provides, and reports the rest."""
    kept: list[Trigger] = []
    for trigger in triggers:
        missing = trigger.needs - source.provides
        if missing:
            log(f"{trigger.name}: disabled (source {source.name} has no {', '.join(sorted(missing))})")
        else:
            kept.append(trigger)
    return kept
