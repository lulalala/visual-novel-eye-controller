"""Fits a gesture's limits to takes you record: some that should fire, some that shouldn't."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, replace

from eyeokuri.config import Config, GestureConfig, StepConfig
from eyeokuri.eyes import Observation
from eyeokuri.triggers import GestureTrigger, Replay, replay, signal_value

# What a take is: the gesture as you mean it, or a near miss that must not fire.
DO = "do"
TOO_QUICK = "too_quick"
TOO_SLOW = "too_slow"
OTHER = "other"
KIND_LABELS = {DO: "should fire", TOO_QUICK: "too quick", TOO_SLOW: "too slow", OTHER: "shouldn't fire"}
# How many times the wizard asks you to do the gesture itself.
DO_TAKES = 3

# Where each signal sits while you just read.
_REST = {"eyes": 1.0, "pitch": 0.0, "yaw": 0.0}
# A step's edge goes this share of the way from rest to your weakest take's peak.
REACH = 0.6
# An edge stays at least this far from rest, so small movements and noise don't count.
_MIN_REACH = {"eyes": 0.15, "pitch": 5.0, "yaw": 5.0}
# The wizard's plot cuts a take to where it gets this share of the way to its peak.
TRIM_SHARE = 0.5
# Space kept between a step's edge and the edge of a box around rest (the hysteresis).
_GAP = {"eyes": 0.1, "pitch": 3.0, "yaw": 3.0}
# A take that moves less than this share of your typical take is a miss and left out.
_MISS = 0.4
# Time limits without a counterexample: the minimum at this share of your
# quickest take, the maximum at this multiple of your slowest plus _SLACK_S.
_MIN_SHARE = 0.6
_MAX_SCALE = 2.0
_SLACK_S = 0.3


@dataclass(frozen=True)
class Take:
    kind: str
    observations: list[Observation]


@dataclass(frozen=True)
class Fit:
    gesture: GestureConfig
    notes: list[str]
    """What changed and why, and takes that were left out."""
    results: list[Replay]
    """The fitted gesture replayed over each take, in take order."""


def script(name: str, do_takes: int = DO_TAKES) -> list[tuple[str, str]]:
    """(kind, what to do) for each take the wizard asks for, in order: the
    gesture ``do_takes`` times, then one of each near miss."""
    steps = suggestions(name)
    return [s for s in steps if s[0] == DO] * do_takes + [s for s in steps if s[0] != DO]


def suggestions(name: str) -> list[tuple[str, str]]:
    """(kind, what to do) for takes worth recording for this gesture."""
    read = (OTHER, "read the screen normally for a few seconds")
    known = {
        "blink": [
            (DO, "blink once, the way you want to advance the text"),
            (TOO_QUICK, "blink once quickly, the way you blink without thinking"),
            (TOO_SLOW, "close your eyes for a few seconds, as if resting them"),
        ],
        "head_shake": [
            (DO, "shake your head once"),
            (TOO_SLOW, "turn slowly to one side, wait, then slowly to the other"),
            (OTHER, "look around the screen naturally"),
        ],
        "nod_down": [(DO, "nod down once"), (TOO_SLOW, "look down for a few seconds"), read],
        "nod_up": [(DO, "nod up once"), (TOO_SLOW, "look up for a few seconds"), read],
    }
    return known.get(name, [(DO, f"do {name} once"), (TOO_SLOW, f"do {name} slowly"), read])


def can_tune(gesture: GestureConfig) -> bool:
    """Only steps with a box can be fitted; a step that is another gesture has none."""
    return all(s.signal for s in gesture.steps)


def trim(observations: list[Observation], signals: set[str], pad_s: float = 0.2) -> tuple[float, list[Observation]]:
    """(start, observations) cut to the part where a signal gets at least
    ``TRIM_SHARE`` of the way to the take's peak, plus ``pad_s`` on each side,
    with times counted from the cut. A take with no movement is kept whole."""
    moved = []
    for s in signals & _REST.keys():
        away = [(o.timestamp, abs(v - _REST[s])) for o in observations if (v := signal_value(s, o)) is not None]
        peak = max((d for _, d in away), default=0.0)
        # A half blink or a glance before the real movement isn't part of it.
        least = max(_MIN_REACH[s], TRIM_SHARE * peak)
        moved += [t for t, d in away if d >= least]
    if not moved:
        return 0.0, observations
    start = max(0.0, min(moved) - pad_s)
    end = max(moved) + pad_s
    return start, [replace(o, timestamp=o.timestamp - start) for o in observations if start <= o.timestamp <= end]


def _excursion(step: StepConfig) -> tuple[str, int] | None:
    """(field, direction) of the edge you cross moving away from rest, or
    None for a box around rest (the "eyes open again" or "back to center" steps)."""
    unit = step.unit
    rest = _REST[step.signal]
    above, below = step.bounds
    if above is not None and above >= rest:
        return f"above_{unit}", 1
    if below is not None and below <= rest:
        return f"below_{unit}", -1
    return None


def _show(signal: str, value: float) -> str:
    return f"{value:.2f}" if signal == "eyes" else f"{value:.0f}°"


def _fit_edges(gesture: GestureConfig, takes: list[tuple[int, Take]], notes: list[str]) -> GestureConfig:
    steps = list(gesture.steps)
    missed: set[int] = set()
    for i, step in enumerate(steps):
        edge = _excursion(step)
        if edge is None:
            continue
        key, d = edge
        signal, rest = step.signal, _REST[step.signal]
        peaks = []
        for n, take in takes:
            values = [v for o in take.observations if (v := signal_value(signal, o)) is not None]
            if values:
                peaks.append((n, max(d * (v - rest) for v in values)))
        if not peaks:
            continue
        typical = statistics.median(p for _, p in peaks)
        if typical < _MIN_REACH[signal]:
            notes.append(f"step {i + 1}: your takes hardly moved {signal}, so its edge stays. "
                         "Redo them, and move further.")
            continue
        used = [p for n, p in peaks if p >= _MISS * typical]
        missed |= {n for n, p in peaks if p < _MISS * typical}
        weakest = min(used)
        reach = max(REACH * weakest, _MIN_REACH[signal])
        # Stay outside every box around rest on this side, so jitter at its
        # edge can't complete the gesture.
        for other in gesture.steps:
            if other.signal == signal and _excursion(other) is None:
                inner = getattr(other, f"{'below' if d > 0 else 'above'}_{other.unit}")
                if inner is not None:
                    reach = max(reach, d * (inner - rest) + _GAP[signal])
        far = getattr(step, f"{'below' if d > 0 else 'above'}_{step.unit}")
        if far is not None:
            reach = min(reach, d * (far - rest) - _GAP[signal])
        value = round(rest + d * reach, 2) if signal == "eyes" else float(round(rest + d * reach))
        old = getattr(step, key)
        if value != old:
            word = "above" if d > 0 else "below"
            notes.append(f"step {i + 1}: {signal} {word} {_show(signal, value)} (was {_show(signal, old)}). "
                         f"Your weakest take reached {_show(signal, rest + d * weakest)}.")
            steps[i] = replace(step, **{key: value})
        if reach > weakest:
            notes.append(f"step {i + 1}: your weakest take didn't reach the edge, which can't be closer "
                         f"to rest, so that take won't fire. Move further when you do the gesture.")
    for n in sorted(missed):
        notes.append(f"take {n}: hardly any movement, so it was left out. Redo it if you missed the cue.")
    return replace(gesture, steps=steps)


def _attempts(name: str, gesture: GestureConfig, take: Take) -> list[tuple[tuple[int, float], ...]]:
    """(step, time) of every match in the take, plus an unfinished one at the
    end with the take's last frame as its next step, so its time is a lower bound."""
    trigger = GestureTrigger(name, gesture)
    found = []
    for obs in take.observations:
        if trigger.update(obs) is not None:
            found.append(trigger.last_attempt)
    pending = trigger.progress()
    if pending and take.observations:
        found.append((*pending, (-1, take.observations[-1].timestamp)))
    return found


def _span(times: list[float]) -> str:
    lo, hi = min(times), max(times)
    return f"{lo:.2f}s" if f"{lo:.2f}" == f"{hi:.2f}" else f"{lo:.2f}-{hi:.2f}s"


def _floor(value: float) -> float:
    return math.floor(value * 100 + 1e-6) / 100


def _ceil(value: float) -> float:
    return math.ceil(value * 100 - 1e-6) / 100


def _fit_min(pos: list[float], neg: list[float]) -> tuple[float, int]:
    """The lowest allowed time, and how many negatives it still lets through."""
    lo = min(pos)
    value = lo * _MIN_SHARE
    below = [n for n in neg if n < lo]
    if below:
        value = max(value, (max(below) + lo) / 2)
    return _floor(value), len(neg) - len(below)


def _fit_max(pos: list[float], neg: list[float]) -> tuple[float, int]:
    hi = max(pos)
    value = hi * _MAX_SCALE + _SLACK_S
    above = [n for n in neg if n > hi]
    if above:
        value = min(value, (min(above) + hi) / 2)
    return max(_ceil(value), 0.01), len(neg) - len(above)


def fit(config: Config, name: str, takes: list[Take]) -> Fit:
    """Fits gesture ``name`` to the takes. Step edges move to match how far
    your takes go; time limits that are set move to fit between your takes and
    the near misses. Limits that are off (0) stay off."""
    gesture = config.gestures[name]
    if not can_tune(gesture):
        raise ValueError(f"gestures.{name}: steps that are other gestures can't be fitted")
    notes: list[str] = []
    numbered = list(enumerate(takes, 1))
    gesture = _fit_edges(gesture, [(n, t) for n, t in numbered if t.kind == DO], notes)

    # Find each take's steps with the fitted edges and no time limits.
    relaxed = replace(
        gesture, within_s=0.0, cooldown_s=0.0,
        steps=[replace(s, after_min_s=0.0, after_max_s=0.0) for s in gesture.steps],
    )
    gaps: dict[str, dict[int, list[float]]] = {k: {} for k in KIND_LABELS}
    totals: dict[str, list[float]] = {k: [] for k in KIND_LABELS}
    for n, take in numbered:
        attempts = _attempts(name, relaxed, take)
        if take.kind != TOO_SLOW:
            # Only a take that is too slow learns from an unfinished attempt.
            attempts = [a for a in attempts if a[-1][0] != -1]
        if not attempts and take.kind == DO:
            notes.append(f"take {n}: the gesture wasn't found, so its timing was left out")
        if not attempts or take.kind == OTHER:
            continue
        # A stray quick blink can share a take with the one you meant, so a
        # take counts as its slowest attempt, or its quickest when it was
        # meant to be too quick.
        pick = min if take.kind == TOO_QUICK else max
        times = pick(attempts, key=lambda a: a[-1][1] - a[0][1])
        totals[take.kind].append(times[-1][1] - times[0][1])
        for (_, before), (i, t) in zip(times, times[1:]):
            if i == -1:
                # Unfinished: whichever step comes next took at least this long.
                reached = {j for j, _ in times}
                left = [j for j in range(len(gesture.steps)) if j not in reached]
                for j in (left if gesture.any_order else left[:1]):
                    gaps[take.kind].setdefault(j, []).append(t - before)
            else:
                gaps[take.kind].setdefault(i, []).append(t - before)

    steps = list(gesture.steps)
    for i, step in enumerate(steps):
        pos = gaps[DO].get(i, [])
        if not pos:
            continue
        changes = {}
        if step.after_min_s:
            changes["after_min_s"], leaks = _fit_min(pos, gaps[TOO_QUICK].get(i, []))
            if leaks:
                notes.append(f"step {i + 1}: {leaks} too-quick take(s) were as slow as your quickest "
                             "take, so they will still fire")
        if step.after_max_s:
            changes["after_max_s"], leaks = _fit_max(pos, gaps[TOO_SLOW].get(i, []))
            if leaks:
                notes.append(f"step {i + 1}: {leaks} too-slow take(s) were as quick as your slowest "
                             "take, so they will still fire")
        for key, value in changes.items():
            old = getattr(step, key)
            if value != old:
                word = "at least" if key == "after_min_s" else "at most"
                notes.append(f"step {i + 1}: {word} {value:.2f}s after the previous step (was {old:.2f}s). "
                             f"Your takes took {_span(pos)}.")
        steps[i] = replace(step, **changes)
    gesture = replace(gesture, steps=steps)

    if gesture.within_s and totals[DO]:
        value, leaks = _fit_max(totals[DO], totals[TOO_SLOW])
        if value != gesture.within_s:
            notes.append(f"whole gesture: within {value:.2f}s (was {gesture.within_s:.2f}s). "
                         f"Your takes took {_span(totals[DO])}.")
        if leaks:
            notes.append(f"whole gesture: {leaks} too-slow take(s) were as quick as your slowest "
                         "take, so they will still fire")
        gesture = replace(gesture, within_s=value)

    fitted = replace(config, gestures={**config.gestures, name: gesture})
    results = [replay(fitted, name, t.observations) for t in takes]
    return Fit(gesture, notes, results)
