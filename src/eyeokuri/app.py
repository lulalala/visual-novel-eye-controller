"""Main loop: source signals -> eye and head state -> triggers -> output."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Any, Callable

from eyeokuri import preview
from eyeokuri.config import Config, apply_overrides, load_config, nested, parse_override
from eyeokuri.engine import Engine, Frame, check_config
from eyeokuri.outputs import OUTPUT_NAMES, check_output_name


def _output_arg(text: str) -> str:
    try:
        check_output_name(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from None
    return text.strip().lower()


# Shortcut flags: (flag, config path, argparse options). Anything else can be
# set with --set SECTION.KEY=VALUE.
_SHORTCUTS: list[tuple[str, str, dict[str, Any]]] = [
    ("--camera", "camera.index", {"type": int, "metavar": "N", "help": "camera index"}),
    ("--min-duration", "gestures.blink.steps.1.after_min_s", {"type": float, "metavar": "S",
     "help": "shortest closure that triggers, in seconds"}),
    ("--blink-key", "gestures.blink.output", {"type": _output_arg, "metavar": "KEY",
     "help": "key, key combination or mouse input to send for a blink, e.g. "
             f"{', '.join(OUTPUT_NAMES[:5])}, f5, ctrl+s"}),
    ("--no-head-shake", "gestures.head_shake.enabled", {"action": "store_const", "const": False,
     "help": "disable the head-shake pause/resume gesture"}),
    ("--no-sound", "feedback.sound", {"action": "store_const", "const": False,
     "help": "don't beep when triggering"}),
]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="eyeokuri",
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


def _number(value: float | None, spec: str) -> str:
    return "" if value is None else format(value, spec)


# The --log columns: a name, and the value from a frame and the start time.
# Numbers only, never images.
_CSV_COLUMNS: list[tuple[str, Callable[[Frame, float], str]]] = [
    ("t", lambda f, start: f"{f.obs.timestamp - start:.3f}"),
    ("face", lambda f, _: str(int(f.obs.face_present))),
    ("left", lambda f, _: _number(f.obs.left, ".4f")),
    ("right", lambda f, _: _number(f.obs.right, ".4f")),
    ("combined", lambda f, _: _number(f.obs.combined, ".4f")),
    ("baseline", lambda f, _: _number(f.obs.baseline, ".4f")),
    ("ready", lambda f, _: str(int(f.obs.ready))),
    ("closed", lambda f, _: str(int(f.obs.closed))),
    ("wink", lambda f, _: _number(f.obs.wink, ".4f")),
    ("head_yaw", lambda f, _: _number(f.obs.head_yaw, ".1f")),
    ("head_pitch", lambda f, _: _number(f.obs.head_pitch, ".1f")),
    ("head_roll", lambda f, _: _number(f.obs.head_roll, ".1f")),
    ("fired", lambda f, _: str(int(f.fired))),
]


def csv_header() -> list[str]:
    return [name for name, _ in _CSV_COLUMNS]


def csv_row(frame: Frame, start: float) -> list[str]:
    return [value(frame, start) for _, value in _CSV_COLUMNS]


def run(config: Config, args: argparse.Namespace) -> int:
    engine = Engine(config, _log)

    log_file = args.log.open("w", newline="") if args.log else None
    log = csv.writer(log_file) if log_file else None
    if log:
        log.writerow(csv_header())

    print("Running. Keep your eyes open normally for a couple of seconds to calibrate.", flush=True)
    start = time.monotonic()
    try:
        while True:
            frame = engine.step()
            obs = frame.obs
            now = obs.timestamp

            if log:
                log.writerow(csv_row(frame, start))

            if args.preview:
                key = preview.show(
                    engine.source.debug_view(), obs, config.eyes, engine.statuses(),
                    engine.paused, engine.fps, now - engine.last_fire_at < preview.FLASH_S,
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
        print(f"eyeokuri: {e}", file=sys.stderr)
        return 2
    return run(config, args)
