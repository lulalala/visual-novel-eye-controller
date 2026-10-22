"""Gestures. Each gesture matches a sequence of steps in the observations.

A step is a box on a plot of one signal over time: a range of values (eyes
below 0.55 of their usual openness, head pitch above 12°) and how soon after
the previous step the signal must enter it. A step can also be another
gesture firing.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Protocol

from eyeokuri.config import RATIO_SIGNALS, SIGNALS, Config, GestureConfig, StepConfig
from eyeokuri.eyes import Observation
from eyeokuri.sources import EYE_OPENNESS, HEAD_POSE, Source


@dataclass(frozen=True)
class TriggerEvent:
    trigger: str
    action: str
    timestamp: float
    detail: str = ""


class Trigger(Protocol):
    name: str
    needs: frozenset[str]
    """Signals the source must provide (see eyeokuri.sources); otherwise the trigger is skipped."""

    def update(self, obs: Observation) -> TriggerEvent | None: ...

    def reset(self) -> None: ...

    def status(self) -> str:
        """Short human-readable state for the preview window."""
        ...


def signal_value(signal: str, obs: Observation) -> float | None:
    """The signal's value this frame, or None if it isn't available."""
    if not obs.face_present:
        return None
    if signal == "eyes":
        if not obs.ready or obs.combined is None or not obs.baseline:
            return None
        return obs.combined / obs.baseline
    if signal == "wink":
        # Positive = left eye closed, like yaw: positive = your left.
        return obs.wink if obs.ready else None
    # Positive pitch = head tilted down; positive yaw = face turned toward
    # the camera image's right, which is your left.
    return obs.head_pitch if signal == "pitch" else obs.head_yaw


class StepWatcher:
    """Reports the frame the signal enters one step's box, or has stayed in it for hold_s."""

    def __init__(self, step: StepConfig) -> None:
        self.step = step
        self._above, self._below = step.bounds
        self._was_inside: bool | None = None
        self._entered_at: float | None = None

    def reset(self) -> None:
        # The next frame only sets where the signal is; already inside doesn't count.
        self._was_inside = None
        self._entered_at = None

    def update(self, value: float, t: float) -> bool:
        inside = (self._above is None or value > self._above) and (
            self._below is None or value < self._below
        )
        was_inside = self._was_inside
        self._was_inside = inside
        if not inside:
            self._entered_at = None
            return False
        if was_inside is False:
            self._entered_at = t
        if self._entered_at is None or t - self._entered_at < self.step.hold_s - 1e-9:
            return False
        self._entered_at = None
        return True


@dataclass(frozen=True)
class _Partial:
    """Steps matched so far: which are left, the first step's time, and the last step."""

    remaining: tuple[int, ...]
    start: float
    last: int
    last_time: float
    times: tuple[tuple[int, float], ...]
    """(step, time) for each step matched so far."""


class GestureTrigger:
    """Fires when its steps' boxes are entered in order, each within its time limits."""

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
        self._steps = config.steps
        self._all = tuple(range(len(config.steps)))
        self._watchers = {i: StepWatcher(s) for i, s in enumerate(config.steps) if s.signal}
        self._gestures = {i: gestures[s.gesture] for i, s in enumerate(config.steps) if s.gesture}
        self._guards = config.guards
        needs = {EYE_OPENNESS if s.signal in RATIO_SIGNALS else HEAD_POSE for s in config.steps if s.signal}
        for gesture in self._gestures.values():
            needs |= gesture.needs
        self.needs = frozenset(needs)
        self._partials: list[_Partial] = []
        self._last_fire: float | None = None
        self._values: dict[str, float | None] = {}
        self.last_attempt: tuple[tuple[int, float], ...] = ()
        """(step, time) of the steps in the last attempt that fired or was rejected."""
        self.fired = False
        """True on the frame this gesture fires, for gestures that use it as a step."""

    def reset(self) -> None:
        for watcher in self._watchers.values():
            watcher.reset()
        self._partials = []

    def update(self, obs: Observation) -> TriggerEvent | None:
        self.fired = False
        t = obs.timestamp
        self._values = {s.signal: signal_value(s.signal, obs) for s in self._steps if s.signal}
        if not obs.face_present or None in self._values.values():
            # Losing the face (or a signal) mid-gesture cancels it.
            if self._partials:
                self._log(f"{self.name}: canceled (face lost)")
            self.reset()
            return None
        outside = self._outside_guard(obs)
        if outside:
            # Like a lost face: a half-done gesture is dropped, and the signal
            # must enter its box again after the head is back.
            if self._partials:
                self._log(f"{self.name}: canceled ({outside})")
            self.reset()
            return None
        arrived = [i for i, w in self._watchers.items() if w.update(self._values[w.step.signal], t)]
        arrived += [i for i, g in self._gestures.items() if g.fired]
        for i in sorted(arrived):
            event = self._arrive(i, t)
            if event is not None:
                return event
        self._expire(t)
        return None

    def _outside_guard(self, obs: Observation) -> str:
        """Why a guard blocks this frame, or an empty string."""
        for guard in self._guards:
            value = signal_value(guard.signal, obs)
            if value is None:
                # A source without head pose still blinks; it just can't tell where you look.
                continue
            above, below = guard.bounds
            if (above is not None and value <= above) or (below is not None and value >= below):
                return f"head {guard.signal} {value:+.0f}° outside its limit"
        return ""

    def _next(self, remaining: tuple[int, ...]) -> tuple[int, ...]:
        return remaining if self.config.any_order else remaining[:1]

    def _arrive(self, i: int, t: float) -> TriggerEvent | None:
        step = self._steps[i]
        advanced: list[_Partial] = []
        kept: list[_Partial] = []
        for p in self._partials:
            if i not in self._next(p.remaining):
                kept.append(p)
                continue
            gap = t - p.last_time
            if step.after_min_s and gap < step.after_min_s:
                # A failed step ends this attempt; the next first step starts a new one.
                self.last_attempt = (*p.times, (i, t))
                self._log(
                    f"{self.name}: step {i + 1} came {gap:.2f}s after step {p.last + 1} "
                    f"(too short, min {step.after_min_s:.2f}s)"
                )
                continue
            advanced.append(
                _Partial(tuple(j for j in p.remaining if j != i), p.start, i, t, (*p.times, (i, t)))
            )
        if i in self._next(self._all):
            advanced.append(_Partial(tuple(j for j in self._all if j != i), t, i, t, ((i, t),)))

        # Keep one partial per remaining set: when a step repeats, the newer one wins.
        latest: dict[tuple[int, ...], _Partial] = {}
        for p in [*kept, *advanced]:
            if p.remaining and (p.remaining not in latest or p.start > latest[p.remaining].start):
                latest[p.remaining] = p
        self._partials = list(latest.values())
        done = [p for p in advanced if not p.remaining]
        if not done:
            return None

        cfg = self.config
        match = max(done, key=lambda p: p.start)
        took = t - match.start
        self.last_attempt = match.times
        detail = f"{len(self._steps)} steps in {took:.2f}s" if len(self._steps) > 1 else "step 1 reached"
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

    def _expire(self, t: float) -> None:
        within = self.config.within_s
        kept: list[_Partial] = []
        for p in self._partials:
            nxt = self._next(p.remaining)
            limits = [self._steps[j].after_max_s for j in nxt]
            if all(limits) and t - p.last_time > max(limits):
                self.last_attempt = p.times
                steps = " or ".join(str(j + 1) for j in nxt)
                self._log(
                    f"{self.name}: step {steps} not reached in time (too long, max {max(limits):.2f}s)"
                )
                continue
            if within and t - p.start > 2 * within:
                # Much older starts aren't attempts at this gesture, so they expire quietly.
                self.last_attempt = p.times
                continue
            kept.append(p)
        self._partials = kept

    def progress(self) -> tuple[tuple[int, float], ...]:
        """(step, time) of the furthest attempt still waiting for its next step."""
        if not self._partials:
            return ()
        return max((p.times for p in self._partials), key=lambda times: (len(times), times[-1][1]))

    def status(self) -> str:
        parts = []
        for signal, value in self._values.items():
            if value is None:
                parts.append(f"no {signal}")
            elif signal in RATIO_SIGNALS:
                parts.append(f"{signal} {value:+.2f}" if signal == "wink" else f"eyes {value:.2f}")
            else:
                parts.append(f"{signal} {value:+.0f}°")
        if len(self._steps) > 1 and self._partials:
            matched = len(self._steps) - min(len(p.remaining) for p in self._partials)
            parts.append(f"{matched}/{len(self._steps)} steps")
        return ", ".join(parts) or "waiting"


@dataclass(frozen=True)
class Replay:
    fired_at: float | None
    reason: str
    """Why it didn't fire, as the log would say it; or when it fired."""
    steps: tuple[tuple[int, float], ...]
    """(step, time) for each step reached in the attempt shown."""


def replay(config: Config, name: str, observations: list[Observation]) -> Replay:
    """Runs gesture ``name`` (enabled or not) over recorded observations, for
    testing settings against your own movement. Stops at the first fire."""
    messages: list[str] = []
    gestures = dict(config.gestures)
    gestures[name] = replace(gestures[name], enabled=True, cooldown_s=0.0)
    triggers = create_triggers(replace(config, gestures=gestures), messages.append)
    target = next(t for t in triggers if t.name == name)
    assert isinstance(target, GestureTrigger)
    for obs in observations:
        for trigger in triggers:
            event = trigger.update(obs)
            if event is not None and trigger is target:
                return Replay(event.timestamp, f"fires at {event.timestamp:.2f}s", target.last_attempt)
    prefix = f"{name}: "
    own = [m[len(prefix):] for m in messages if m.startswith(prefix)]
    pending = target.progress()
    if pending and len(pending) >= len(target.last_attempt):
        reason = f"waiting for the next step when the recording ended (after step {pending[-1][0] + 1})"
        return Replay(None, reason, pending)
    if own:
        return Replay(None, own[-1], target.last_attempt)
    if target.last_attempt:
        within = gestures[name].within_s
        return Replay(None, f"didn't finish in time (too slow, max {within:.2f}s)", target.last_attempt)
    return Replay(None, "step 1 never reached", ())


def _validate(name: str, config: GestureConfig) -> None:
    key = f"gestures.{name}"
    if not config.steps:
        raise ValueError(f"{key}.steps must list at least one step")
    for i, step in enumerate(config.steps):
        sk = f"{key}.steps[{i}]"
        if bool(step.signal) == bool(step.gesture):
            raise ValueError(
                f"{sk} must set either signal ({', '.join(SIGNALS)}) or gesture, "
                f"not {'both' if step.signal else 'neither'}"
            )
        bounds = {f: getattr(step, f) for f in ("above_ratio", "below_ratio", "above_deg", "below_deg")}
        if step.gesture:
            if any(v is not None for v in bounds.values()):
                raise ValueError(f"{sk}: a gesture step has no box, so remove its above_/below_ keys")
        elif step.signal not in SIGNALS:
            raise ValueError(f"{sk}.signal must be one of {', '.join(SIGNALS)}, not {step.signal!r}")
        else:
            unit = step.unit
            other = "deg" if unit == "ratio" else "ratio"
            if bounds[f"above_{other}"] is not None or bounds[f"below_{other}"] is not None:
                raise ValueError(
                    f"{sk}: {step.signal} uses above_{unit}/below_{unit}, not above_{other}/below_{other}"
                )
            above, below = step.bounds
            if above is None and below is None:
                raise ValueError(f"{sk} needs above_{unit}, below_{unit} or both")
            if above is not None and below is not None and above >= below:
                raise ValueError(
                    f"{sk}.above_{unit} must be below {sk}.below_{unit} ({below}), not {above}"
                )
        for field_name in ("after_min_s", "after_max_s", "hold_s"):
            value = getattr(step, field_name)
            if value < 0:
                raise ValueError(f"{sk}.{field_name} must be 0 or more, not {value}")
        if step.after_max_s and step.after_max_s < step.after_min_s:
            raise ValueError(
                f"{sk}.after_max_s must be 0 (no limit) or at least {sk}.after_min_s "
                f"({step.after_min_s}), not {step.after_max_s}"
            )
    for i, guard in enumerate(config.guards):
        gk = f"{key}.guards[{i}]"
        if guard.signal not in ("pitch", "yaw"):
            raise ValueError(f"{gk}.signal must be pitch or yaw, not {guard.signal!r}")
        if guard.gesture or guard.above_ratio is not None or guard.below_ratio is not None:
            raise ValueError(f"{gk}: a guard uses only signal, above_deg and below_deg")
        if guard.after_min_s or guard.after_max_s or guard.hold_s:
            raise ValueError(f"{gk}: a guard has no timing, so remove after_min_s, after_max_s and hold_s")
        above, below = guard.bounds
        if above is None and below is None:
            raise ValueError(f"{gk} needs above_deg, below_deg or both")
        if above is not None and below is not None and above >= below:
            raise ValueError(f"{gk}.above_deg must be below {gk}.below_deg ({below}), not {above}")
    for field_name in ("within_s", "cooldown_s"):
        value = getattr(config, field_name)
        if value < 0:
            raise ValueError(f"{key}.{field_name} must be 0 or more, not {value}")


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
        for i, step in enumerate(cfg.steps):
            if not step.gesture:
                continue
            if step.gesture not in gestures:
                raise ValueError(
                    f"gestures.{name}.steps[{i}].gesture: unknown gesture {step.gesture!r}; "
                    f"choose from {', '.join(gestures)}"
                )
            if not gestures[step.gesture].enabled:
                raise ValueError(
                    f"gestures.{name}.steps[{i}].gesture: {step.gesture} is disabled "
                    f"(gestures.{step.gesture}.enabled = false)"
                )
            build(step.gesture, (*chain, name))
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
