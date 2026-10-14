"""Gestures. Each gesture matches a sequence of poses (or other gestures) in the observations.

A pose is a position you hold for a while, such as eyes closed or head
turned left. A pose tracker reports a span, from entering the pose to
leaving it. A gesture fires once its steps' spans happen in order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from vn_eye.config import POSES, Config, GestureConfig
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


@dataclass(frozen=True)
class Span:
    """One step that happened: a pose held, or a gesture that fired."""

    step: str
    start: float
    end: float


# Head poses: (signal, direction). Positive pitch = head tilted down; positive
# yaw = face turned toward the camera image's right, which is your left.
_HEAD_POSES = {
    "head_down": ("pitch", 1),
    "head_up": ("pitch", -1),
    "head_left": ("yaw", 1),
    "head_right": ("yaw", -1),
}


class PoseTracker:
    """Reports a span each time the pose is entered and then left."""

    def __init__(self, pose: str, config: GestureConfig) -> None:
        self.pose = pose
        self._config = config
        self._since: float | None = None
        self._last_held = 0.0
        self._value: float | None = None

    @property
    def active(self) -> bool:
        return self._since is not None

    def reset(self) -> None:
        self._since = None

    def update(self, obs: Observation) -> tuple[bool, Span | None]:
        """Returns (signal available, span that just ended)."""
        inside = self._inside(obs)
        if inside is None:
            self.reset()
            return False, None
        t = obs.timestamp
        if inside and self._since is None:
            self._since = t
        elif not inside and self._since is not None:
            span = Span(self.pose, self._since, t)
            self._since = None
            self._last_held = span.end - span.start
            return True, span
        if self._since is not None:
            self._last_held = t - self._since
        return True, None

    def _inside(self, obs: Observation) -> bool | None:
        if self.pose == "eyes_closed":
            # Eye poses share [eyes] close_ratio/open_ratio, which also decide
            # which samples the open-eye baseline learns from.
            return obs.closed if obs.face_present and obs.ready else None
        signal, direction = _HEAD_POSES[self.pose]
        value = obs.head_pitch if signal == "pitch" else obs.head_yaw
        self._value = value
        if not obs.face_present or value is None:
            return None
        if self._since is None:
            return value * direction > self._config.past_deg
        return value * direction > self._config.release_deg

    def status(self) -> str:
        if self._since is not None:
            return f"{self.pose} {self._last_held:.2f}s"
        if self.pose == "eyes_closed":
            return f"open (last closure {self._last_held:.2f}s)"
        signal, _ = _HEAD_POSES[self.pose]
        return f"no {signal}" if self._value is None else f"{signal} {self._value:+.0f}°"


@dataclass(frozen=True)
class _Partial:
    """Steps matched so far: what is left, and when the first step started."""

    remaining: tuple[str, ...]
    start: float
    last_end: float


class GestureTrigger:
    """Fires when its steps happen in order, each one ending before the next starts."""

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
        self._poses = {s: PoseTracker(s, config) for s in dict.fromkeys(self._steps) if s in POSES}
        self._gestures = [gestures[s] for s in dict.fromkeys(self._steps) if s not in POSES]
        needs: set[str] = set()
        for pose in self._poses:
            needs.add(EYE_OPENNESS if pose == "eyes_closed" else HEAD_POSE)
        for gesture in self._gestures:
            needs |= gesture.needs
        self.needs = frozenset(needs)
        self._partials: list[_Partial] = []
        self._last_fire: float | None = None
        self.fired: Span | None = None
        """Set on the frame this gesture fires, for gestures that use it as a step."""

    def reset(self) -> None:
        for tracker in self._poses.values():
            tracker.reset()
        self._partials = []

    def update(self, obs: Observation) -> TriggerEvent | None:
        self.fired = None
        spans: list[Span] = []
        lost = not obs.face_present
        for tracker in self._poses.values():
            was_active = tracker.active
            available, span = tracker.update(obs)
            if not available:
                lost = True
                if was_active:
                    self._log(f"{self.name}: {tracker.pose} canceled (face lost)")
            elif span is not None:
                spans.append(span)
        if lost:
            # Losing the face (or the signal) mid-gesture cancels it.
            self.reset()
            return None
        spans += [g.fired for g in self._gestures if g.fired is not None]

        t = obs.timestamp
        within = self.config.within_s
        if within:
            # Much older starts aren't attempts at this gesture, so they expire quietly.
            self._partials = [p for p in self._partials if t - p.start <= 2 * within]
        for span in sorted(spans, key=lambda s: s.start):
            event = self._step(span, t)
            if event is not None:
                return event
        return None

    def _step(self, span: Span, t: float) -> TriggerEvent | None:
        held = span.end - span.start
        cfg = self.config
        if cfg.hold_min_s and held < cfg.hold_min_s:
            self._log(f"{self.name}: {span.step} {held:.2f}s (too short, min {cfg.hold_min_s:.2f}s)")
            return None
        if cfg.hold_max_s and held > cfg.hold_max_s:
            self._log(f"{self.name}: {span.step} {held:.2f}s (too long, max {cfg.hold_max_s:.2f}s)")
            return None

        candidates = [p for p in self._partials if span.start >= p.last_end]
        candidates.append(_Partial(self._steps, span.start, span.start))
        advanced = [_advance(p, span, cfg.any_order) for p in candidates]
        advanced = [p for p in advanced if p is not None]
        done = [p for p in advanced if not p.remaining]
        # Keep one partial per remaining state: when a step repeats, the newer one wins.
        latest: dict[tuple[str, ...], _Partial] = {}
        for p in [*self._partials, *advanced]:
            if p.remaining and (p.remaining not in latest or p.start > latest[p.remaining].start):
                latest[p.remaining] = p
        self._partials = list(latest.values())
        if not done:
            return None

        match = max(done, key=lambda p: p.start)
        took = span.end - match.start
        if len(self._steps) == 1:
            detail = f"{span.step} {held:.2f}s"
        else:
            detail = f"{len(self._steps)} steps in {took:.2f}s"
        if cfg.within_s and took > cfg.within_s:
            self._log(f"{self.name}: {detail} (too slow, max {cfg.within_s:.2f}s)")
            return None
        if self._last_fire is not None and t - self._last_fire < cfg.cooldown_s:
            self._log(f"{self.name}: {detail} (cooldown {cfg.cooldown_s:.2f}s)")
            return None
        self._last_fire = t
        # The step that completed this match can't start the next one.
        self._partials = []
        self.fired = Span(self.name, match.start, span.end)
        return TriggerEvent(self.name, self.name, t, detail)

    def status(self) -> str:
        parts = [tracker.status() for tracker in self._poses.values()]
        if len(self._steps) > 1 and self._partials:
            matched = len(self._steps) - min(len(p.remaining) for p in self._partials)
            parts.append(f"{matched}/{len(self._steps)} steps")
        return ", ".join(dict.fromkeys(parts)) or "waiting"


def _advance(partial: _Partial, span: Span, any_order: bool) -> _Partial | None:
    remaining = partial.remaining
    if any_order:
        if span.step not in remaining:
            return None
        i = remaining.index(span.step)
    elif remaining[0] == span.step:
        i = 0
    else:
        return None
    return _Partial(remaining[:i] + remaining[i + 1 :], partial.start, span.end)


def _validate(name: str, config: GestureConfig) -> None:
    key = f"gestures.{name}"
    if not config.steps or not all(isinstance(s, str) for s in config.steps):
        raise ValueError(f"{key}.steps must list at least one pose or gesture name")
    for field_name in ("hold_min_s", "hold_max_s", "within_s", "cooldown_s"):
        value = getattr(config, field_name)
        if value < 0:
            raise ValueError(f"{key}.{field_name} must be 0 or more, not {value}")
    if config.hold_max_s and config.hold_max_s < config.hold_min_s:
        raise ValueError(
            f"{key}.hold_max_s must be 0 (no limit) or at least {key}.hold_min_s "
            f"({config.hold_min_s}), not {config.hold_max_s}"
        )
    if any(s in _HEAD_POSES for s in config.steps) and not (
        0 <= config.release_deg < config.past_deg
    ):
        # With release_deg >= past_deg, the pose would end on the frame it starts.
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
            if step in POSES:
                continue
            if step not in gestures:
                raise ValueError(
                    f"gestures.{name}.steps: unknown step {step!r}; use a pose "
                    f"({', '.join(POSES)}) or another gesture's name"
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
