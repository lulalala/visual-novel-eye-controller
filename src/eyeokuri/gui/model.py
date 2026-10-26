"""Gesture settings as plain dicts for the editor, the plot's ranges and the camera view's size. No Tk, so it is unit-tested."""

from __future__ import annotations

import re
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eyeokuri.config import CameraConfig, GestureConfig, StepConfig
from eyeokuri.eyes import Observation
from eyeokuri.i18n import N_
from eyeokuri.triggers import Replay
from eyeokuri.tuning import DO, Take, trim


# Seconds of signal kept for "Live" and for saving a test recording.
RECORD_S = 4.0
# Wider camera frames are scaled down to this for the camera view.
VIEW_MAX_WIDTH = 640

@dataclass(frozen=True)
class SignalPlot:
    """How the plot draws one signal's lane. Its highlighted line is the
    signal's rest value, and its unit symbol comes from config.SIGNALS."""

    lo: float
    hi: float
    grid: tuple[float, ...]
    """Values that get a grid line."""
    snap: float
    """A dragged edge snaps to a multiple of this."""
    hint: str
    new_box: tuple[float | None, float | None]
    """(above, below) of a step you add for this signal."""


SIGNAL_PLOTS = {
    "eyes": SignalPlot(0.0, 1.3, (0.0, 0.25, 0.5, 0.75, 1.0, 1.25), 0.01,
                       N_("Eyes: openness, 1.0 = your usual open level"), (None, 0.55)),
    "wink": SignalPlot(-1.0, 1.0, (-1.0, -0.5, 0.0, 0.5, 1.0), 0.01,
                       N_("Wink: right eye minus left, + = left eye closed"), (0.25, None)),
    "pitch": SignalPlot(-40.0, 50.0, (-40, -20, 0, 20, 40, 50), 0.5,
                        N_("Head pitch: + = tilted down"), (12.0, None)),
    "yaw": SignalPlot(-60.0, 60.0, (-60, -40, -20, 0, 20, 40, 60), 0.5,
                      N_("Head yaw: + = turned to your left"), (15.0, None)),
}
GESTURE_NAME = re.compile(r"[A-Za-z0-9_-]+")
# A gesture that sent its output: Engine logs "<name>: <detail> -> <output>".
_FIRED = re.compile(r" -> [^\s()]+$")


def log_tag(message: str) -> str:
    """The log window's tag for a log line: ``fire`` for a gesture that sent
    its output, ``reject`` for one that didn't and why, in parentheses."""
    if _FIRED.search(message):
        return "fire"
    if message.endswith(")") and " (" in message:
        return "reject"
    return ""


def fmt(value: float | None) -> str:
    return "" if value is None else f"{value:g}"


def gesture_model(gesture: GestureConfig) -> dict[str, Any]:
    """The gesture as the editor's plain dicts, which its widgets change in place.
    A step's ``kind`` is a signal name or "gesture"; ``above``/``below`` hold
    its bounds in the signal's own unit. gesture_config() is the inverse."""
    steps = []
    for s in gesture.steps:
        if s.gesture:
            above = below = None
        else:
            above, below = s.bounds
        steps.append({
            "kind": "gesture" if s.gesture else s.signal, "gesture": s.gesture,
            "above": above, "below": below,
            "after_min_s": s.after_min_s, "after_max_s": s.after_max_s, "hold_s": s.hold_s,
        })
    guards = [{"kind": g.signal, "above": g.above_deg, "below": g.below_deg} for g in gesture.guards]
    return {
        "guards": guards,
        "enabled": gesture.enabled, "output": gesture.output, "any_order": gesture.any_order,
        "within_s": gesture.within_s, "cooldown_s": gesture.cooldown_s, "steps": steps,
    }


def gesture_config(model: dict[str, Any]) -> GestureConfig:
    """The settings for the editor's dicts; GestureConfig does the validating, later."""
    steps = []
    for s in model["steps"]:
        timing = {"after_min_s": s["after_min_s"], "after_max_s": s["after_max_s"]}
        if s["kind"] == "gesture":
            steps.append(StepConfig(gesture=s["gesture"], **timing))
        else:
            unit = StepConfig(signal=s["kind"]).unit
            steps.append(StepConfig(
                signal=s["kind"], hold_s=s["hold_s"],
                **{f"above_{unit}": s["above"], f"below_{unit}": s["below"]}, **timing,
            ))
    guards = [StepConfig(signal=g["kind"], above_deg=g["above"], below_deg=g["below"])
              for g in model["guards"]]
    return GestureConfig(
        enabled=model["enabled"], steps=steps, guards=guards, any_order=model["any_order"],
        within_s=model["within_s"], cooldown_s=model["cooldown_s"], output=model["output"],
    )


def new_step(kind: str) -> dict[str, Any]:
    above, below = SIGNAL_PLOTS[kind].new_box if kind in SIGNAL_PLOTS else (None, None)
    return {"kind": kind, "gesture": "", "above": above, "below": below,
            "after_min_s": 0.0, "after_max_s": 1.0, "hold_s": 0.0}


def users_of(gestures: dict[str, GestureConfig], name: str) -> list[str]:
    """The gestures that have ``name`` as one of their steps, so deleting it would break them."""
    return [n for n, g in gestures.items() if n != name and any(s.gesture == name for s in g.steps)]


def view_size(camera: CameraConfig) -> tuple[int, int]:
    """The camera view's width and height in pixels for these camera settings."""
    if camera.width <= VIEW_MAX_WIDTH:
        return camera.width, camera.height
    return VIEW_MAX_WIDTH, round(camera.height * VIEW_MAX_WIDTH / camera.width)


def find_notice_file(name: str, folders: list[Path]) -> Path | None:
    """The first file called `name` in the folders, for the About window's license buttons."""
    for folder in folders:
        candidate = folder / name
        if candidate.is_file():
            return candidate
    return None


@dataclass(frozen=True)
class WizardTraces:
    main: list[Observation]
    result: Replay | None
    others: list[tuple[list[Observation], str]]
    """Thin traces behind the main one, each with a tone: ``ok``, ``bad`` or ``plain``."""
    duration: float
    boxes: bool = True
    """Whether to draw the gesture's step boxes: not while recording, when nothing is fitted yet."""


def wizard_traces(takes: list[Take | None], results: dict[int, Replay], picked: int | None, signals: set[str],
                  on_review: bool, live: list[Observation] | None = None) -> WizardTraces:
    """What the wizard plots. Every take is cut to where it moves and counted
    from that cut. The picked take is the main trace; on the review page the
    others are toned by whether they do what they should. While recording,
    ``live`` is the main trace, uncut and without a result."""
    main: list[Observation] = list(live) if live is not None else []
    result: Replay | None = None
    others: list[tuple[list[Observation], str]] = []
    for j, take in enumerate(takes):
        if take is None:
            continue
        start, cut = trim(take.observations, signals)
        found = results[j]
        if j == picked and live is None:
            main = cut
            result = Replay(None if found.fired_at is None else found.fired_at - start, found.reason,
                            tuple((s, t - start) for s, t in found.steps))
        elif on_review:
            others.append((cut, "ok" if (found.fired_at is not None) == (take.kind == DO) else "bad"))
        else:
            others.append((cut, "plain"))
    length = max((c[-1].timestamp for c in [main, *(o for o, _ in others)] if c), default=0.0)
    if live is not None:
        duration = max(RECORD_S, math.ceil(length))
    else:
        duration = max(1.0, math.ceil(length)) if length else RECORD_S
    return WizardTraces(main, result, others, duration, boxes=live is None)
