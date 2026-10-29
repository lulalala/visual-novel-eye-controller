"""Fits a gesture's limits to takes you record: some that should fire, some that shouldn't."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, replace

from eyeokuri.config import SIGNALS, Config, GestureConfig, StepConfig
from eyeokuri.eyes import Observation
from eyeokuri.i18n import N_, _, colon, gap, stop
from eyeokuri.labels import show_signal
from eyeokuri.triggers import GestureTrigger, Replay, replay, signal_value

# What a take is: the gesture as you mean it, or a near miss that must not fire.
DO = "do"
TOO_QUICK = "too_quick"
TOO_SLOW = "too_slow"
OTHER = "other"
KIND_LABELS = {DO: N_("Should fire"), TOO_QUICK: N_("Too quick"), TOO_SLOW: N_("Too slow"), OTHER: N_("Shouldn't fire")}
# How many times the wizard asks you to do the gesture itself.
DO_TAKES = 3

# Each signal's rest value, minimum reach and gap are in config.SIGNALS.
# A step's edge goes this share of the way from rest to your weakest take's peak.
REACH = 0.6
# The wizard's plot cuts a take to where it gets this share of the way to its peak.
TRIM_SHARE = 0.5
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
    changes: list[str]
    """What changed and why."""
    warnings: list[str]
    """Takes that were left out or won't do what they should, and why."""
    results: list[Replay]
    """The fitted gesture replayed over each take, in take order."""


def script(name: str, do_takes: int = DO_TAKES) -> list[tuple[str, str]]:
    """(kind, what to do) for each take the wizard asks for, in order: the
    gesture ``do_takes`` times, then one of each near miss."""
    steps = suggestions(name)
    return [s for s in steps if s[0] == DO] * do_takes + [s for s in steps if s[0] != DO]


_READ = (OTHER, N_("Read the screen normally for a few seconds."))
# (kind, what to do) for each built-in gesture; every one in config._default_gestures() needs an entry.
_SCRIPTS = {
    "blink": [
        (DO, N_("Blink once, the way you want to advance the text.")),
        (TOO_QUICK, N_("Blink once quickly, the way you blink without thinking.")),
        (TOO_SLOW, N_("Close your eyes for a few seconds, as if resting them.")),
    ],
    "wink_left": [
        (DO, N_("Wink your left eye once.")),
        (TOO_SLOW, N_("Close your left eye for a few seconds, as if resting it.")),
        (OTHER, N_("Blink both eyes a few times, the way you blink without thinking.")),
    ],
    "wink_right": [
        (DO, N_("Wink your right eye once.")),
        (TOO_SLOW, N_("Close your right eye for a few seconds, as if resting it.")),
        (OTHER, N_("Blink both eyes a few times, the way you blink without thinking.")),
    ],
    "head_shake": [
        (DO, N_("Shake your head once.")),
        (TOO_SLOW, N_("Turn your head slowly to one side, wait, then slowly to the other, as if looking around the room.")),
        (OTHER, N_("Look around the screen naturally.")),
    ],
    "nod_down": [(DO, N_("Nod down once.")), (TOO_SLOW, N_("Tilt your head down and hold it for a few seconds, as if reading the bottom of the screen.")), _READ],
    "nod_up": [(DO, N_("Nod up once.")), (TOO_SLOW, N_("Tilt your head up and hold it for a few seconds, as if looking above the screen.")), _READ],
    "tilt_right": [
        (DO, N_("Tilt your head toward your right shoulder, hold it for a second, then straighten up.")),
        (OTHER, N_("Shake your head once.")),
        _READ,
    ],
    "tilt_left": [
        (DO, N_("Tilt your head toward your left shoulder, hold it for a second, then straighten up.")),
        (OTHER, N_("Shake your head once.")),
        _READ,
    ],
}
# For gestures you add.
_GENERIC_SCRIPT = [(DO, N_("Do the gesture once.")), (TOO_SLOW, N_("Do the gesture slowly.")), _READ]


def suggestions(name: str) -> list[tuple[str, str]]:
    """(kind, what to do) for takes worth recording for this gesture."""
    return list(_SCRIPTS.get(name, _GENERIC_SCRIPT))


def can_tune(gesture: GestureConfig) -> bool:
    """Only steps with a box can be fitted; a step that is another gesture has none."""
    return all(s.signal for s in gesture.steps)


def trim(observations: list[Observation], signals: set[str], pad_s: float = 0.2) -> tuple[float, list[Observation]]:
    """(start, observations) cut to the part where a signal gets at least
    ``TRIM_SHARE`` of the way to the take's peak, plus ``pad_s`` on each side,
    with times counted from the cut. A take with no movement is kept whole."""
    moved = []
    for s in signals & SIGNALS.keys():
        spec = SIGNALS[s]
        away = [(o.timestamp, abs(v - spec.rest)) for o in observations if (v := signal_value(s, o)) is not None]
        peak = max((d for _, d in away), default=0.0)
        # A half blink or a glance before the real movement isn't part of it.
        least = max(spec.min_reach, TRIM_SHARE * peak)
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
    rest = SIGNALS[step.signal].rest
    above, below = step.bounds
    if above is not None and above >= rest:
        return f"above_{unit}", 1
    if below is not None and below <= rest:
        return f"below_{unit}", -1
    return None


def _step_label(i: int, signal: str) -> str:
    return _("Step") + f" {i + 1} · " + show_signal(signal) + colon()


def _show(signal: str, value: float) -> str:
    return SIGNALS[signal].show(value)


def _peak(away: list[float]) -> float:
    """The furthest a take got from rest and stayed for two frames in a row, so
    one stray landmark frame doesn't set the edge."""
    pairs = [min(a, b) for a, b in zip(away, away[1:])]
    return max(pairs) if pairs else max(away)


def _away(take: Take, signal: str, rest: float, d: int) -> list[float]:
    return [d * (v - rest) for o in take.observations if (v := signal_value(signal, o)) is not None]


def _fit_edges(gesture: GestureConfig, takes: list[tuple[int, Take]], changes: list[str], warnings: list[str],
               avoid: list[tuple[int, Take]]) -> tuple[GestureConfig, set[int]]:
    """Moves each step's edge to match ``takes``; ``avoid`` are takes that
    shouldn't fire, whose edge is kept above their peak when there's room.
    Also returns the takes left out for hardly moving."""
    steps = list(gesture.steps)
    missed: set[int] = set()
    for i, step in enumerate(steps):
        edge = _excursion(step)
        if edge is None:
            continue
        key, d = edge
        signal = step.signal
        spec = SIGNALS[signal]
        rest = spec.rest
        peaks = []
        for n, take in takes:
            values = _away(take, signal, rest, d)
            if values:
                peaks.append((n, _peak(values)))
        if not peaks:
            continue
        typical = statistics.median(p for _, p in peaks)
        if typical < spec.min_reach:
            warnings.append(_step_label(i, signal) + _("Your takes hardly moved, so the edge stays.")
                            + gap() + _("Redo them, and move further."))
            continue
        used = [p for n, p in peaks if p >= _MISS * typical]
        missed |= {n for n, p in peaks if p < _MISS * typical}
        weakest = min(used)
        reach = max(REACH * weakest, spec.min_reach)
        # Stay outside every box around rest on this side, so jitter at its
        # edge can't complete the gesture.
        for other in gesture.steps:
            if other.signal == signal and _excursion(other) is None:
                inner = getattr(other, f"{'below' if d > 0 else 'above'}_{other.unit}")
                if inner is not None:
                    reach = max(reach, d * (inner - rest) + spec.gap)
        # A take that shouldn't fire but moves further than the edge: raise the
        # edge between it and your weakest take, if that leaves room.
        reached = [(n, _peak(v)) for n, t in avoid if (v := _away(t, signal, rest, d))]
        blockers = [(n, p) for n, p in reached if reach <= p < weakest]
        if blockers:
            reach = max(reach, (max(p for _, p in blockers) + weakest) / 2)
        far = getattr(step, f"{'below' if d > 0 else 'above'}_{step.unit}")
        if far is not None:
            reach = min(reach, d * (far - rest) - spec.gap)
        value = spec.round(rest + d * reach)
        old = getattr(step, key)
        if value != old:
            # A short sentence, then labeled values, so a translation never has to reorder them.
            changes.append(_step_label(i, signal) + _("Edge moved.") + gap()
                           + _("Now:") + f" {_show(signal, value)}" + stop() + gap()
                           + _("Was:") + f" {_show(signal, old)}" + stop() + gap()
                           + _("Your weakest take:") + f" {_show(signal, rest + d * weakest)}" + stop()
                           + (gap() + _("Kept clear of these \"shouldn't fire\" takes:")
                              + f" {', '.join(str(n) for n, _n in blockers)}" + stop() if blockers else ""))
            steps[i] = replace(step, **{key: value})
        if reach > weakest:
            warnings.append(_step_label(i, signal)
                            + _("Your weakest take didn't reach the edge, which can't be closer to rest, so that take won't fire.")
                            + gap() + _("Move further when you do the gesture."))
    for n in sorted(missed):
        warnings.append(_("Take") + f" {n}: " + _("Hardly any movement, so it was left out.")
                        + gap() + _("Redo it if you missed the cue."))
    return replace(gesture, steps=steps), missed


def _attempts(name: str, gesture: GestureConfig, take: Take) -> list[tuple[tuple[int, float], ...]]:
    """(step, time) of every match in the take, plus an unfinished one at the
    end with the take's last frame as its next step, so its time is a lower bound."""
    trigger = GestureTrigger(name, gesture)
    found = []
    for obs in take.observations:
        event = trigger.update(obs)
        if event is not None and not event.ended:
            found.append(trigger.last_attempt)
    pending = trigger.progress()
    if pending and take.observations:
        found.append((*pending, (-1, take.observations[-1].timestamp)))
    return found


def _span(times: list[float]) -> str:
    lo, hi = min(times), max(times)
    return f"{lo:.2f}s" if f"{lo:.2f}" == f"{hi:.2f}" else f"{lo:.2f}-{hi:.2f}s"


def _window(step: StepConfig) -> str:
    """The step's time limits after the previous step, in symbols rather than words."""
    lo, hi = step.after_min_s, step.after_max_s
    if lo and hi:
        return f"{lo:.2f}-{hi:.2f}s"
    return f"≥{lo:.2f}s" if lo else f"≤{hi:.2f}s"


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


def fit(config: Config, name: str, takes: list[Take], numbers: list[int] | None = None) -> Fit:
    """Fits gesture ``name`` to the takes. Step edges move to match how far
    your takes go, and clear of takes that shouldn't fire when they can; time
    limits that are set move to fit between your takes and the near misses.
    Limits that are off (0) stay off. Messages call the takes by ``numbers``
    (1, 2, 3, ... by default), so they match what you saw while recording."""
    numbered = list(zip(numbers or range(1, len(takes) + 1), takes))
    result = _fit(config, name, numbered, [])
    firing = [(n, t) for (n, t), r in zip(numbered, result.results)
              if t.kind == OTHER and r.fired_at is not None]
    if not firing:
        return result
    result = _fit(config, name, numbered, firing)
    still = {n for (n, _), r in zip(numbered, result.results) if r.fired_at is not None}
    for n, _take in firing:
        if n in still:
            result.warnings.append(
                _("Take") + f" {n}: "
                + _("It shouldn't fire but still does, and no setting tells it apart from your takes that should.")
                + gap() + _("Redo it, or do the gesture more differently."))
    return result


def _fit(config: Config, name: str, numbered: list[tuple[int, Take]], avoid: list[tuple[int, Take]]) -> Fit:
    gesture = config.gestures[name]
    if not can_tune(gesture):
        raise ValueError(f"gestures.{name}: steps that are other gestures can't be fitted")
    changes: list[str] = []
    warnings: list[str] = []
    gesture, missed = _fit_edges(gesture, [(n, t) for n, t in numbered if t.kind == DO], changes, warnings, avoid)

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
        if not attempts and take.kind == DO and n not in missed:
            warnings.append(_("Take") + f" {n}: " + _("The gesture wasn't found, so its timing was left out."))
        if not attempts or take.kind == OTHER:
            continue
        # A stray quick blink can share a take with the one you meant, so a
        # take counts as its slowest attempt, or its quickest when it was
        # meant to be too quick.
        pick = min if take.kind == TOO_QUICK else max
        times = pick(attempts, key=lambda a: a[-1][1] - a[0][1])
        totals[take.kind].append(times[-1][1] - times[0][1])
        for (_step, before), (i, t) in zip(times, times[1:]):
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
        limits = {}
        if step.after_min_s:
            limits["after_min_s"], leaks = _fit_min(pos, gaps[TOO_QUICK].get(i, []))
            if leaks:
                warnings.append(_("Step") + f" {i + 1}: " + _("Too-quick takes that still fire:") + f" {leaks}" + stop() + gap()
                                + _("They were as slow as your quickest take."))
        if step.after_max_s:
            limits["after_max_s"], leaks = _fit_max(pos, gaps[TOO_SLOW].get(i, []))
            if leaks:
                warnings.append(_("Step") + f" {i + 1}: " + _("Too-slow takes that still fire:") + f" {leaks}" + stop() + gap()
                                + _("They were as quick as your slowest take."))
        timed = replace(step, **limits)
        if timed != step:
            changes.append(_("Step") + f" {i + 1}: " + _("Time after the previous step changed.") + gap()
                           + _("Now:") + f" {_window(timed)}" + stop() + gap() + _("Was:") + f" {_window(step)}" + stop() + gap()
                           + _("Your takes:") + f" {_span(pos)}" + stop())
        steps[i] = timed
    gesture = replace(gesture, steps=steps)

    if gesture.within_s and totals[DO]:
        value, leaks = _fit_max(totals[DO], totals[TOO_SLOW])
        if value != gesture.within_s:
            changes.append(_("Whole gesture:") + " " + _("Time limit changed.") + gap()
                           + _("Now:") + f" {value:.2f}s" + stop() + gap() + _("Was:") + f" {gesture.within_s:.2f}s" + stop() + gap()
                           + _("Your takes:") + f" {_span(totals[DO])}" + stop())
        if leaks:
            warnings.append(_("Whole gesture:") + " " + _("Too-slow takes that still fire:") + f" {leaks}" + stop() + gap()
                            + _("They were as quick as your slowest take."))
        gesture = replace(gesture, within_s=value)

    fitted = replace(config, gestures={**config.gestures, name: gesture})
    results = [replay(fitted, name, t.observations) for _, t in numbered]
    return Fit(gesture, changes, warnings, results)
