"""Settings, loaded from an optional TOML file on top of built-in defaults."""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field, fields, is_dataclass, replace
from pathlib import Path
from typing import Any

from eyeokuri.i18n import CATALOGS
from eyeokuri.sources import EYE_OPENNESS, HEAD_POSE


@dataclass(frozen=True)
class CameraConfig:
    index: int = 0
    width: int = 640
    height: int = 480
    fps: int = 30

    def __post_init__(self) -> None:
        # Drivers pick their own mode for sizes they don't support, and a tiny
        # frame has no usable face.
        if self.index < 0:
            raise ValueError(f"camera.index must be 0 or more, not {self.index}")
        if self.width < 160:
            raise ValueError(f"camera.width must be at least 160, not {self.width}")
        if self.height < 120:
            raise ValueError(f"camera.height must be at least 120, not {self.height}")
        if self.fps < 1:
            raise ValueError(f"camera.fps must be at least 1, not {self.fps}")


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
    # Head yaw, pitch and roll are measured relative to a rolling median of your usual pose.
    baseline_window_s: float = 10.0
    # Seconds to learn before head gestures can trigger.
    warmup_s: float = 2.0


@dataclass(frozen=True)
class SignalSpec:
    """What a step's signal is. triggers.signal_value() reads it from an Observation."""

    unit: str
    """ratio (relative to your usual level) or deg: the suffix of a step's bound fields."""
    needs: str
    """What the source must provide for it (see eyeokuri.sources)."""
    rest: float
    """Where the signal sits while you just read."""
    min_reach: float
    """tuning.fit() keeps a step's edge at least this far from rest, so noise doesn't count."""
    gap: float
    """tuning.fit() keeps this much space between an edge and a box around rest (the hysteresis)."""
    guard: bool = False
    """A guard (a head limit) can use it."""

    @property
    def symbol(self) -> str:
        """Shown after a value."""
        return "°" if self.unit == "deg" else ""

    def show(self, value: float, signed: bool = False) -> str:
        """The value as the log and the wizard show it: ratios to 0.01, angles to whole degrees."""
        places = 2 if self.unit == "ratio" else 0
        return f"{value:{'+' if signed else ''}.{places}f}{self.symbol}"

    def round(self, value: float) -> float:
        """The value as precise as show() shows it."""
        return round(value, 2) if self.unit == "ratio" else float(round(value))


# Everything a step can watch. Adding one also needs signal_value() in
# triggers.py and a plot lane (SIGNAL_PLOTS in gui/model.py).
SIGNALS: dict[str, SignalSpec] = {
    "eyes": SignalSpec("ratio", EYE_OPENNESS, rest=1.0, min_reach=0.15, gap=0.1),
    "wink": SignalSpec("ratio", EYE_OPENNESS, rest=0.0, min_reach=0.2, gap=0.1),
    "pitch": SignalSpec("deg", HEAD_POSE, rest=0.0, min_reach=5.0, gap=3.0, guard=True),
    "yaw": SignalSpec("deg", HEAD_POSE, rest=0.0, min_reach=5.0, gap=3.0, guard=True),
    "roll": SignalSpec("deg", HEAD_POSE, rest=0.0, min_reach=5.0, gap=3.0),
}
GUARD_SIGNALS = tuple(name for name, spec in SIGNALS.items() if spec.guard)


@dataclass(frozen=True)
class StepConfig:
    # What to watch: eyes (openness, 1.0 = your usual open level), wink (right
    # eye's openness minus the left's, positive = left eye closed), pitch
    # (degrees, positive = head tilted down), yaw (degrees, positive = your
    # left) or roll (degrees of sideways tilt, positive = toward your left).
    signal: str = ""
    # Instead of a signal: another gesture's name. The step counts when it fires.
    gesture: str = ""
    # The step's box: the step counts the moment the signal enters it. Eyes
    # and wink use the _ratio bounds, the head the _deg bounds. Leave one out for a box
    # that is open on that side.
    above_ratio: float | None = None
    below_ratio: float | None = None
    above_deg: float | None = None
    below_deg: float | None = None
    # Time allowed since the previous step. 0 means no limit.
    after_min_s: float = 0.0
    after_max_s: float = 0.0
    # Stay inside the box this long before the step counts.
    hold_s: float = 0.0

    @property
    def unit(self) -> str:
        """The suffix of this step's bound fields: ratio for eyes and wink, deg for the head."""
        return SIGNALS[self.signal].unit if self.signal in SIGNALS else "deg"

    @property
    def bounds(self) -> tuple[float | None, float | None]:
        """(above, below) of the box, from the fields its signal uses."""
        if self.unit == "ratio":
            return self.above_ratio, self.below_ratio
        return self.above_deg, self.below_deg


@dataclass(frozen=True)
class GestureConfig:
    enabled: bool = True
    # Boxes to reach in order (see StepConfig).
    steps: list[StepConfig] = field(default_factory=list, metadata={"item": StepConfig})
    # Boxes the head must stay inside for the gesture to count (a signal,
    # above_/below_ bounds). Outside one, the gesture is canceled and can't
    # start. Only signal and the bounds are used.
    guards: list[StepConfig] = field(default_factory=list, metadata={"item": StepConfig})
    # Also accept the steps in any order (a shake can start on either side).
    any_order: bool = False
    # Time allowed from the first step to the last. 0 means no limit.
    within_s: float = 0.0
    # The gesture is ignored this long after it last fired.
    cooldown_s: float = 1.0
    # A key (a-z, 0-9, f1-f24, enter, space, tab, escape, page_down, up, ...),
    # optionally after modifiers (ctrl+s, shift+tab); or a mouse input:
    # mouse_left_click, mouse_right_click, mouse_wheel_down. App-level outputs: app_pause_toggle.
    # Empty: send nothing (for a gesture that is only a step of another gesture).
    output: str = ""
    # press: send the output once. while: hold it down when the gesture fires,
    # and let go when the signal leaves the box of the step that completed it
    # (some games skip text while ctrl is held).
    output_mode: str = "press"


def _default_gestures() -> dict[str, GestureConfig]:
    # A head returns "to center" by entering a box around 0. Its edge (8°) is
    # inside the first step's edge (12°), so jitter at 12° can't complete a nod.
    # Looking away from the screen (head turned or tilted) makes blinks and
    # eye readings unreliable, so blink only counts with the head near center.
    # The pitch limit (10°) is inside the nods' edge (12°), so a nod cancels a
    # blink that its eye movement would otherwise complete.
    straight = [
        StepConfig(signal="yaw", above_deg=-20.0, below_deg=20.0),
        StepConfig(signal="pitch", above_deg=-10.0, below_deg=10.0),
    ]
    center = {"above_deg": -8.0, "below_deg": 8.0, "after_max_s": 0.8}
    # A wink is one eye at least 0.25 less open than the other, then both level
    # again within 0.6 s. after_min_s keeps out a blink where one eye closes a
    # frame later; after_max_s, squinting or rubbing one eye.
    level = {"above_ratio": -0.15, "below_ratio": 0.15, "after_min_s": 0.05, "after_max_s": 0.6}
    return {
        # 0.1 s lets most natural blinks advance the text; raise after_min_s
        # (e.g. 0.35-0.45) to require a deliberate closure. Holding the eyes
        # shut past after_max_s (resting them, looking away) cancels.
        "blink": GestureConfig(
            steps=[
                StepConfig(signal="eyes", below_ratio=0.6),
                StepConfig(signal="eyes", above_ratio=0.7, after_min_s=0.1, after_max_s=1.0),
            ],
            guards=straight, cooldown_s=1.0, output="enter",
        ),
        "wink_left": GestureConfig(
            enabled=False,
            steps=[StepConfig(signal="wink", above_ratio=0.25), StepConfig(signal="wink", **level)],
            guards=straight, cooldown_s=1.0,
        ),
        "wink_right": GestureConfig(
            enabled=False,
            steps=[StepConfig(signal="wink", below_ratio=-0.25), StepConfig(signal="wink", **level)],
            guards=straight, cooldown_s=1.0,
        ),
        "head_shake": GestureConfig(
            steps=[StepConfig(signal="yaw", above_deg=15.0), StepConfig(signal="yaw", below_deg=-15.0)],
            any_order=True, within_s=1.5, cooldown_s=1.5, output="app_pause_toggle",
        ),
        "nod_up": GestureConfig(
            enabled=False,
            steps=[StepConfig(signal="pitch", below_deg=-12.0), StepConfig(signal="pitch", **center)],
            cooldown_s=1.0, output="up",
        ),
        "nod_down": GestureConfig(
            enabled=False,
            steps=[StepConfig(signal="pitch", above_deg=12.0), StepConfig(signal="pitch", **center)],
            cooldown_s=1.0, output="down",
        ),
        # Tilting your head toward a shoulder past 15° for 0.3 s; with "while",
        # ctrl stays down (skipping text in many games) until you straighten up.
        "tilt_right": GestureConfig(
            steps=[StepConfig(signal="roll", below_deg=-15.0, hold_s=0.3)],
            cooldown_s=0.5, output="ctrl", output_mode="while",
        ),
        "tilt_left": GestureConfig(
            enabled=False,
            steps=[StepConfig(signal="roll", above_deg=15.0, hold_s=0.3)],
            cooldown_s=0.5,
        ),
    }


@dataclass(frozen=True)
class FeedbackConfig:
    sound: bool = True
    # Print every gesture that didn't trigger (too short, too long, cooldown...).
    log_rejected: bool = True


@dataclass(frozen=True)
class AppConfig:
    # Start paused: gestures are detected and logged but send nothing. The GUI
    # saves this whenever you pause or resume, so it starts the way you left it.
    paused: bool = False
    # GUI language: "auto" follows the Windows display language; "en" or a
    # translation's code (ja, zh-TW) picks one. The command line is always English.
    language: str = "auto"

    def __post_init__(self) -> None:
        allowed = ("auto", "en", *sorted(CATALOGS))
        if self.language not in allowed:
            raise ValueError(f"app.language must be one of {', '.join(allowed)}, not {self.language!r}")


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
    feedback: FeedbackConfig = field(default_factory=FeedbackConfig)
    app: AppConfig = field(default_factory=AppConfig)


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
        elif isinstance(current, list) and "item" in known[key].metadata:
            changes[key] = _merge_list(current, value, known[key].metadata["item"], f"{path}{key}")
        else:
            # Fields that default to None are optional numbers.
            expected = float if current is None else type(current)
            if expected is float and isinstance(value, int) and not isinstance(value, bool):
                value = float(value)
            if type(value) is not expected:
                raise ValueError(
                    f"Config key {path}{key} should be {expected.__name__}, "
                    f"got {type(value).__name__}"
                )
            changes[key] = value
    return replace(obj, **changes)


def _merge_list(current: list[Any], value: Any, item: Any, path: str) -> list[Any]:
    """A list of tables replaces the list. A table keyed by index changes items
    in place, which is what ``--set gestures.blink.steps.1.after_min_s=0.4`` gives."""
    if isinstance(value, list):
        merged = []
        for i, entry in enumerate(value):
            if not isinstance(entry, dict):
                raise ValueError(f"Config key {path}[{i}] must be a table")
            merged.append(_merge(item(), entry, f"{path}[{i}]."))
        return merged
    if isinstance(value, dict):
        merged = list(current)
        for index, entry in value.items():
            if not index.isdigit() or int(index) >= len(merged):
                raise ValueError(
                    f"Config key {path}.{index}: use an index from 0 to {len(merged) - 1}"
                )
            if not isinstance(entry, dict):
                raise ValueError(f"Config key {path}[{index}] must be a table")
            merged[int(index)] = _merge(merged[int(index)], entry, f"{path}[{index}].")
        return merged
    raise ValueError(f"Config key {path} must be a list of tables")


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        # JSON string escapes are valid TOML basic-string escapes.
        return json.dumps(value)
    if isinstance(value, list):
        rows = []
        for item in value:
            base = type(item)()
            parts = [f"{f.name} = {_toml_value(getattr(item, f.name))}" for f in fields(item)
                     if getattr(item, f.name) != getattr(base, f.name)]
            rows.append(f"  {{ {', '.join(parts)} }},")
        return "[\n" + "\n".join(rows) + "\n]"
    raise TypeError(f"Can't write {value!r} as TOML")


def _toml_key(key: str) -> str:
    return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else json.dumps(key)


def gesture_lines(gestures: dict[str, GestureConfig], reference: dict[str, GestureConfig]) -> list[str]:
    """TOML sections with the gesture fields that differ from ``reference``. A gesture
    that isn't in ``reference`` is written with its steps, so it can be read back on its own."""
    lines: list[str] = []
    for name, gesture in gestures.items():
        ref = reference.get(name)
        if gesture == ref:
            continue
        lines += ["", f"[gestures.{_toml_key(name)}]"]
        for gf in fields(GestureConfig):
            v = getattr(gesture, gf.name)
            if v != getattr(ref or GestureConfig(), gf.name) or (ref is None and gf.name == "steps"):
                lines.append(f"{gf.name} = {_toml_value(v)}")
    return lines


def dump_config(config: Config) -> str:
    """TOML with the values that differ from the defaults; load_config reads it back."""
    default = Config()
    lines = [f"version = {CONFIG_VERSION}"]
    for f in fields(Config):
        value, base = getattr(config, f.name), getattr(default, f.name)
        if f.name == "version" or value == base:
            continue
        if f.name == "gestures":
            lines += gesture_lines(value, base)
        else:
            lines += ["", f"[{f.name}]"]
            lines += [f"{sf.name} = {_toml_value(getattr(value, sf.name))}" for sf in fields(value)
                      if getattr(value, sf.name) != getattr(base, sf.name)]
    return "\n".join(lines) + "\n"


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
            f"{path} has {found}, so it uses a layout this eyeokuri can't read. "
            f"Start again from config.example.toml (version = {CONFIG_VERSION})."
        )
    return _merge(config, data, "")


def apply_overrides(config: Config, overrides: dict[str, Any]) -> Config:
    """Apply nested overrides, e.g. {"eyes": {"open_ratio": 0.8}}."""
    return _merge(config, overrides, "")


def parse_override(text: str) -> dict[str, Any]:
    """Turn ``section.key=value`` into a nested dict.

    The value is read as TOML (``0.5``, ``true``, ``"enter"``); anything that
    isn't valid TOML is taken as a plain string, so ``gestures.blink.output=space`` works.
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
