"""Settings, loaded from an optional TOML file on top of built-in defaults."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields, is_dataclass, replace
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CameraConfig:
    index: int = 0
    width: int = 640
    height: int = 480
    fps: int = 30


@dataclass(frozen=True)
class EyeConfig:
    # Openness is tracked relative to a rolling "eyes open" baseline so the
    # thresholds adapt to the user's face, camera angle and posture.
    baseline_window_s: float = 10.0
    warmup_s: float = 2.0
    # Eyes count as closed below baseline * close_ratio and open again above
    # baseline * open_ratio (hysteresis avoids flicker around one threshold).
    close_ratio: float = 0.55
    open_ratio: float = 0.75
    # Both eyes must close (a wink or a squint with one eye won't trigger).
    require_both_eyes: bool = True


@dataclass(frozen=True)
class HeadConfig:
    # Head yaw is measured relative to a rolling median of your usual pose.
    baseline_window_s: float = 10.0


@dataclass(frozen=True)
class BlinkConfig:
    enabled: bool = True
    # Shortest closure that triggers. 0.15 s lets most natural blinks advance
    # the text; raise it (e.g. 0.35-0.45) to require a deliberate closure.
    min_duration_s: float = 0.15
    # Fires when the eyes reopen. Closures longer than this are ignored
    # (resting your eyes, looking away), so holding them shut cancels.
    max_duration_s: float = 2.0
    # Ignore closures while the head is turned further than this (you are
    # looking away, or shaking your head, which often comes with a blink).
    max_head_yaw_deg: float = 12.0
    # Per-trigger cooldown after firing. 0 disables it; blink then relies only
    # on output.cooldown_s, which is shared with all other gestures. Set this
    # to a non-zero value to rate-limit blink independently of head gestures.
    cooldown_s: float = 0.0


@dataclass(frozen=True)
class HeadShakeConfig:
    enabled: bool = True
    # Turn past amplitude_deg to one side, then past it to the other side,
    # within max_duration_s.
    amplitude_deg: float = 15.0
    max_duration_s: float = 1.0
    cooldown_s: float = 1.5


@dataclass(frozen=True)
class HeadNodConfig:
    enabled: bool = False
    # Tilt past amplitude_deg up or down to trigger.
    amplitude_deg: float = 15.0
    cooldown_s: float = 1.0


@dataclass(frozen=True)
class NodConfig:
    enabled: bool = False
    # Tilt past amplitude_deg and return to neutral within max_duration_s.
    amplitude_deg: float = 12.0
    max_duration_s: float = 0.8
    cooldown_s: float = 1.0


@dataclass(frozen=True)
class OutputConfig:
    # Maps trigger event names to outputs.
    # Keystroke outputs: enter, space, left_click, wheel_down, up, down.
    # App-level outputs: app:toggle_pause.
    actions: dict[str, str] = field(
        default_factory=lambda: {
            "blink": "enter",
            "head_shake": "app:toggle_pause",
            "head_nod_up": "up",
            "head_nod_down": "down",
            "nod_up": "up",
            "nod_down": "down",
        }
    )
    # Minimum time between any two triggers firing. This is the only cooldown
    # for blink (unless blink.cooldown_s is also set). Head gestures have their
    # own per-trigger cooldown on top of this.
    cooldown_s: float = 1.0
    dry_run: bool = False


@dataclass(frozen=True)
class FeedbackConfig:
    sound: bool = True
    # Print every gesture that didn't trigger (too short, too long, cooldown...).
    log_rejected: bool = True


@dataclass(frozen=True)
class Config:
    camera: CameraConfig = field(default_factory=CameraConfig)
    eyes: EyeConfig = field(default_factory=EyeConfig)
    head: HeadConfig = field(default_factory=HeadConfig)
    blink: BlinkConfig = field(default_factory=BlinkConfig)
    head_shake: HeadShakeConfig = field(default_factory=HeadShakeConfig)
    head_nod: HeadNodConfig = field(default_factory=HeadNodConfig)
    nod: NodConfig = field(default_factory=NodConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    feedback: FeedbackConfig = field(default_factory=FeedbackConfig)


def _merge(obj: Any, data: dict[str, Any], path: str) -> Any:
    known = {f.name: f for f in fields(obj)}
    changes: dict[str, Any] = {}
    for key, value in data.items():
        if key not in known:
            raise ValueError(f"Unknown config key: {path}{key}")
        current = getattr(obj, key)
        if is_dataclass(current):
            if not isinstance(value, dict):
                raise ValueError(f"Config section {path}{key} must be a table")
            changes[key] = _merge(current, value, f"{path}{key}.")
        elif isinstance(current, dict):
            changes[key] = {**current, **value}
        else:
            if isinstance(current, float) and isinstance(value, int):
                value = float(value)
            if type(value) is not type(current):
                raise ValueError(
                    f"Config key {path}{key} should be {type(current).__name__}, "
                    f"got {type(value).__name__}"
                )
            changes[key] = value
    return replace(obj, **changes)


def load_config(path: Path | None) -> Config:
    config = Config()
    if path is None:
        return config
    with path.open("rb") as f:
        return _merge(config, tomllib.load(f), "")


def apply_overrides(config: Config, overrides: dict[str, Any]) -> Config:
    """Apply nested overrides, e.g. {"blink": {"min_duration_s": 0.5}}."""
    return _merge(config, overrides, "")


def parse_override(text: str) -> dict[str, Any]:
    """Turn ``section.key=value`` into a nested dict.

    The value is read as TOML (``0.5``, ``true``, ``"enter"``); anything that
    isn't valid TOML is taken as a plain string, so ``actions.blink=space`` works.
    """
    key, sep, raw = text.partition("=")
    if not sep or not key.strip():
        raise ValueError(f"Expected KEY=VALUE, got {text!r}")
    try:
        value = tomllib.loads(f"v = {raw.strip()}")["v"]
    except tomllib.TOMLDecodeError:
        value = raw.strip()
    return nested(key.strip(), value)


def nested(path: str, value: Any) -> dict[str, Any]:
    """``nested("a.b", 1)`` -> ``{"a": {"b": 1}}``."""
    result: dict[str, Any] = {}
    node = result
    parts = path.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value
    return result
