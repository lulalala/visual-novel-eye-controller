"""Main loop: source signals -> eye and head state -> triggers -> output."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Any

from vn_eye import preview
from vn_eye.config import Config, apply_overrides, load_config, nested, parse_override
from vn_eye.engine import Engine
from vn_eye.eyes import EyeStateTracker
from vn_eye.head import HeadTracker
from vn_eye.outputs import OUTPUT_NAMES
from vn_eye.triggers import create_triggers

FLASH_S = 0.3


# Shortcut flags: (flag, config path, argparse options). Anything else can be
# set with --set SECTION.KEY=VALUE.
_SHORTCUTS: list[tuple[str, str, dict[str, Any]]] = [
    ("--camera", "camera.index", {"type": int, "metavar": "N", "help": "camera index"}),
    ("--min-duration", "gestures.blink.steps.1.after_min_s", {"type": float, "metavar": "S",
     "help": "shortest closure that triggers, in seconds"}),
    ("--blink-key", "gestures.blink.output", {"choices": OUTPUT_NAMES,
     "help": "what key or mouse input to send for a blink"}),
    ("--no-head-shake", "gestures.head_shake.enabled", {"action": "store_const", "const": False,
     "help": "disable the head-shake pause/resume gesture"}),
    ("--no-sound", "feedback.sound", {"action": "store_const", "const": False,
     "help": "don't beep when triggering"}),
]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="vn-eye",
        description=__doc__,
        epilog="Precedence: built-in defaults < --config file < shortcut flags < --set.",
    )
    p.add_argument("-c", "--config", type=Path, help="TOML config file (see config.example.toml)")
    p.add_argument("--preview", action="store_true", help="show the camera debug window")
    p.add_argument("--log", type=Path, help="write per-frame eye values to a CSV file (no images)")
    # Stops after this many seconds; for scripted --log captures, so not in --help.
    p.add_argument("--duration", type=float, help=argparse.SUPPRESS)
    settings = p.add_argument_group("settings (override the config file)")
    for flag, path, options in _SHORTCUTS:
        settings.add_argument(flag, dest=path, default=None, **options)
    settings.add_argument(
        "--set", action="append", default=[], metavar="SECTION.KEY=VALUE",
        help="set any config value, e.g. --set eyes.open_ratio=0.8 (repeatable)",
    )
    return p.parse_args(argv)


APP_OUTPUTS = frozenset({"app:toggle_pause"})


def validate_outputs(config: Config) -> None:
    for name, gesture in config.gestures.items():
        output = gesture.output
        if output == "":
            continue
        if output.startswith("app:"):
            if output not in APP_OUTPUTS:
                raise ValueError(
                    f"gestures.{name}.output: unknown app output {output!r}; "
                    f"choose from {', '.join(sorted(APP_OUTPUTS))}"
                )
        elif output not in OUTPUT_NAMES:
            raise ValueError(
                f"gestures.{name}.output: unknown output {output!r}; "
                f"choose from {', '.join(OUTPUT_NAMES)}, or \"\" for none"
            )


def check_config(config: Config) -> None:
    """Raises ValueError for settings that would fail later, before the camera opens."""
    validate_outputs(config)
    EyeStateTracker(config.eyes)
    HeadTracker(config.head)
    create_triggers(config)


def build_config(args: argparse.Namespace) -> Config:
    config = load_config(args.config)
    for _, path, _ in _SHORTCUTS:
        value = getattr(args, path)
        if value is not None:
            config = apply_overrides(config, nested(path, value))
    for item in args.set:
        config = apply_overrides(config, parse_override(item))
    check_config(config)
    return config


def _log(message: str) -> None:
    print(message, flush=True)


def run(config: Config, args: argparse.Namespace) -> int:
    engine = Engine(config, _log)

    log_file = args.log.open("w", newline="") if args.log else None
    log = csv.writer(log_file) if log_file else None
    if log:
        log.writerow(["t", "face", "left", "right", "combined", "baseline", "ready", "closed", "head_yaw", "head_pitch", "fired"])

    print("Running. Keep your eyes open normally for a couple of seconds to calibrate.", flush=True)
    start = time.monotonic()
    try:
        while True:
            frame = engine.step()
            obs = frame.obs
            now = obs.timestamp

            if log:
                log.writerow([
                    f"{now - start:.3f}", int(obs.face_present),
                    *(f"{v:.4f}" if v is not None else "" for v in
                      (obs.left, obs.right, obs.combined, obs.baseline)),
                    int(obs.ready), int(obs.closed),
                    f"{obs.head_yaw:.1f}" if obs.head_yaw is not None else "",
                    f"{obs.head_pitch:.1f}" if obs.head_pitch is not None else "", int(frame.fired),
                ])

            if args.preview:
                key = preview.show(
                    engine.source.debug_view(), obs, config.eyes, engine.statuses(),
                    engine.paused, engine.fps, now - engine.last_fire_at < FLASH_S,
                )
                if key in (ord("q"), 27):
                    break
                if key == ord("p"):
                    engine.toggle_pause()

            if args.duration is not None and now - start >= args.duration:
                break
    except KeyboardInterrupt:
        pass
    finally:
        engine.close()
        if args.preview:
            preview.close()
        if log_file:
            log_file.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = build_config(args)
    except (ValueError, OSError) as e:
        print(f"vn-eye: {e}", file=sys.stderr)
        return 2
    return run(config, args)
