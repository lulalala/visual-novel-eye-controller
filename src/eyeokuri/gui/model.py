"""Gesture settings as plain dicts for the editor, and the plot's ranges. No Tk, so it is unit-tested."""

from __future__ import annotations

import re
from typing import Any

from eyeokuri.config import GestureConfig, StepConfig


# Seconds of signal kept for "Live" and for saving a test recording.
RECORD_S = 4.0

# Plot ranges per signal: (min, max, grid lines, unit, value snap when dragging).
PLOT_RANGES: dict[str, tuple[float, float, tuple[float, ...], str, float]] = {
    "eyes": (0.0, 1.3, (0.0, 0.25, 0.5, 0.75, 1.0, 1.25), "", 0.01),
    "pitch": (-40.0, 50.0, (-40, -20, 0, 20, 40, 50), "°", 0.5),
    "yaw": (-60.0, 60.0, (-60, -40, -20, 0, 20, 40, 60), "°", 0.5),
}
LANE_HINTS = {
    "eyes": "Eyes: openness, 1.0 = your usual open level",
    "pitch": "Head pitch: + = tilted down",
    "yaw": "Head yaw: + = turned to your left",
}
GESTURE_NAME = re.compile(r"[A-Za-z0-9_-]+")


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
    above, below = {"eyes": (None, 0.55), "pitch": (12.0, None), "yaw": (15.0, None)}.get(kind, (None, None))
    return {"kind": kind, "gesture": "", "above": above, "below": below,
            "after_min_s": 0.0, "after_max_s": 1.0, "hold_s": 0.0}
