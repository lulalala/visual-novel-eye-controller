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
class GestureConfig:
    enabled: bool = True
    # States to reach in order. A step counts the moment you reach that
    # state. A step can also name another gesture, which counts when that
    # gesture fires. States: see STATES.
    steps: list[str] = field(default_factory=list)
    # Also accept the steps in any order (a shake can start on either side).
    any_order: bool = False
    # The head counts as down/up/left/right past past_deg, and as back at
    # center once it is within release_deg again (the gap between the two
    # stops jitter at the edge). Eye states use [eyes] close_ratio/open_ratio.
    past_deg: float = 15.0
    release_deg: float = 10.0
    # Time allowed between two steps in a row. 0 means no limit.
    gap_min_s: float = 0.0
    gap_max_s: float = 0.0
    # Time allowed from the first step to the last. 0 means no limit.
    within_s: float = 0.0
    # The gesture is ignored this long after it last fired.
    cooldown_s: float = 1.0
    # Keystroke outputs: enter, space, left_click, wheel_down, up, down.
    # App-level outputs: app:toggle_pause. Empty: send nothing (for a gesture
    # that is only a step of another gesture).
    output: str = ""


STATES = (
    "eyes_closed", "eyes_open",
    "head_down", "head_up", "head_left", "head_right", "head_center",
)


def _default_gestures() -> dict[str, GestureConfig]:
    return {
        # 0.15 s lets most natural blinks advance the text; raise gap_min_s
        # (e.g. 0.35-0.45) to require a deliberate closure. Holding the eyes
        # shut past gap_max_s (resting them, looking away) cancels.
        "blink": GestureConfig(
            steps=["eyes_closed", "eyes_open"], gap_min_s=0.15, gap_max_s=2.0,
            cooldown_s=1.0, output="enter",
        ),
        "head_shake": GestureConfig(
            steps=["head_left", "head_right"], any_order=True,
            past_deg=15.0, release_deg=10.0, within_s=1.0, cooldown_s=1.5,
            output="app:toggle_pause",
        ),
        "nod_up": GestureConfig(
            enabled=False, steps=["head_up", "head_center"], past_deg=12.0, release_deg=8.0,
            gap_max_s=0.8, cooldown_s=1.0, output="up",
        ),
        "nod_down": GestureConfig(
            enabled=False, steps=["head_down", "head_center"], past_deg=12.0, release_deg=8.0,
            gap_max_s=0.8, cooldown_s=1.0, output="down",
        ),
    }


@dataclass(frozen=True)
class OutputConfig:
    dry_run: bool = False


@dataclass(frozen=True)
class FeedbackConfig:
    sound: bool = True
    # Print every gesture that didn't trigger (too short, too long, cooldown...).
    log_rejected: bool = True


CONFIG_VERSION = 1


@dataclass(frozen=True)
class Config:
    # Files without this version use an older layout and are rejected.
    version: int = CONFIG_VERSION
    camera: CameraConfig = field(default_factory=CameraConfig)
    eyes: EyeConfig = field(default_factory=EyeConfig)
    head: HeadConfig = field(default_factory=HeadConfig)
    # Built-in gestures can be changed or disabled; new names add gestures.
    gestures: dict[str, GestureConfig] = field(
        default_factory=_default_gestures, metadata={"item": GestureConfig}
    )
    output: OutputConfig = field(default_factory=OutputConfig)
    feedback: FeedbackConfig = field(default_factory=FeedbackConfig)


def _merge(obj: Any, data: dict[str, Any], path: str) -> Any:
    known = {f.name: f for f in fields(obj)}
    changes: dict[str, Any] = {}
    for key, value in data.items():
        if key not in known:
            raise ValueError(f"Unknown config key: {path}{key}")
        current = getattr(obj, key)
        if is_dataclass(current) or isinstance(current, dict):
            if not isinstance(value, dict):
                raise ValueError(f"Config section {path}{key} must be a table")
        if is_dataclass(current):
            changes[key] = _merge(current, value, f"{path}{key}.")
        elif isinstance(current, dict):
            item = known[key].metadata["item"]
            merged = dict(current)
            for name, table in value.items():
                if not isinstance(table, dict):
                    raise ValueError(f"Config section {path}{key}.{name} must be a table")
                merged[name] = _merge(current.get(name, item()), table, f"{path}{key}.{name}.")
            changes[key] = merged
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
        data = tomllib.load(f)
    version = data.get("version")
    if version != CONFIG_VERSION:
        found = "no version key" if version is None else f"version = {version!r}"
        raise ValueError(
            f"{path} has {found}, so it uses a layout this vn-eye can't read. "
            f"Start again from config.example.toml (version = {CONFIG_VERSION})."
        )
    return _merge(config, data, "")


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
