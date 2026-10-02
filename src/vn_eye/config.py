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
class BackendConfig:
    name: str = "mediapipe"
    # "auto", "cpu" or "gpu". Auto picks GPU on macOS and CPU elsewhere.
    delegate: str = "auto"


@dataclass(frozen=True)
class EyeConfig:
    # "ear": eye aspect ratio from landmarks; "blendshape": MediaPipe's eyeBlink scores.
    metric: str = "ear"
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
class LongBlinkConfig:
    enabled: bool = True
    # Normal blinks last ~100-400 ms; a deliberate closure is longer.
    min_duration_s: float = 0.35
    # Closures longer than this are ignored (resting your eyes, looking away).
    max_duration_s: float = 2.0
    # "reopen": fire when the eyes reopen (allows cancelling by holding past max).
    # "hold": fire as soon as min_duration_s is reached (lower latency).
    fire_on: str = "reopen"
    action: str = "next"


@dataclass(frozen=True)
class OutputConfig:
    # Maps trigger actions to an output: enter, space, left_click, wheel_down.
    actions: dict[str, str] = field(default_factory=lambda: {"next": "enter"})
    cooldown_s: float = 1.0
    dry_run: bool = False


@dataclass(frozen=True)
class FeedbackConfig:
    sound: bool = True
    # Print every closure that didn't trigger (too short, too long, cooldown...).
    log_blinks: bool = True


@dataclass(frozen=True)
class HotkeyConfig:
    # pynput GlobalHotKeys syntax. Empty string disables the global hotkey.
    pause: str = "<ctrl>+<alt>+p"


@dataclass(frozen=True)
class Config:
    camera: CameraConfig = field(default_factory=CameraConfig)
    backend: BackendConfig = field(default_factory=BackendConfig)
    eyes: EyeConfig = field(default_factory=EyeConfig)
    long_blink: LongBlinkConfig = field(default_factory=LongBlinkConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    feedback: FeedbackConfig = field(default_factory=FeedbackConfig)
    hotkeys: HotkeyConfig = field(default_factory=HotkeyConfig)


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
    """Apply nested overrides, e.g. {"long_blink": {"min_duration_s": 0.5}}."""
    return _merge(config, overrides, "")


def parse_override(text: str) -> dict[str, Any]:
    """Turn ``section.key=value`` into a nested dict.

    The value is read as TOML (``0.5``, ``true``, ``"enter"``); anything that
    isn't valid TOML is taken as a plain string, so ``fire_on=hold`` works.
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
