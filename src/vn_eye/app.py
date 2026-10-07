"""Main loop: source signals -> eye and head state -> triggers -> output."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from vn_eye import preview
from vn_eye.config import Config, apply_overrides, load_config, nested, parse_override
from vn_eye.eyes import EyeStateTracker
from vn_eye.feedback import play_sound
from vn_eye.head import HeadTracker
from vn_eye.hotkeys import PauseSwitch
from vn_eye.outputs import OUTPUT_NAMES, ActionDispatcher, create_output
from vn_eye.sources.opencv import OpenCVSource
from vn_eye.triggers import TriggerEvent, create_triggers, supported_triggers

_FLASH_S = 0.3


# Shortcut flags: (flag, config path, argparse options). Anything else can be
# set with --set SECTION.KEY=VALUE.
_SHORTCUTS: list[tuple[str, str, dict[str, Any]]] = [
    ("--camera", "camera.index", {"type": int, "metavar": "N", "help": "camera index"}),
    ("--min-duration", "blink.min_duration_s", {"type": float, "metavar": "S",
     "help": "shortest closure that triggers, in seconds"}),
    ("--max-duration", "blink.max_duration_s", {"type": float, "metavar": "S",
     "help": "longer closures are canceled, in seconds"}),
    ("--fire-on", "blink.fire_on", {"choices": ["reopen", "hold"],
     "help": "fire when the eyes reopen, or as soon as --min-duration is reached"}),
    ("--output", "output.actions.blink", {"choices": OUTPUT_NAMES,
     "help": "what key to send for a blink"}),
    ("--cooldown", "output.cooldown_s", {"type": float, "metavar": "S",
     "help": "minimum time between triggers, in seconds"}),
    ("--close-ratio", "eyes.close_ratio", {"type": float, "metavar": "R",
     "help": "closed below baseline * R (lower = needs a firmer closure)"}),
    ("--shake-degrees", "head_shake.amplitude_deg", {"type": float, "metavar": "DEG",
     "help": "how far to turn the head each way for the pause/resume shake"}),
    ("--no-head-shake", "head_shake.enabled", {"action": "store_const", "const": False,
     "help": "disable the head-shake pause/resume gesture"}),
    ("--dry-run", "output.dry_run", {"action": "store_const", "const": True,
     "help": "print actions instead of sending input"}),
    ("--no-sound", "feedback.sound", {"action": "store_const", "const": False,
     "help": "don't beep when triggering"}),
    ("--no-rejected-log", "feedback.log_rejected", {"action": "store_const", "const": False,
     "help": "don't print gestures that didn't trigger"}),
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
    p.add_argument("--duration", type=float, help="stop after this many seconds")
    settings = p.add_argument_group("settings (override the config file)")
    for flag, path, options in _SHORTCUTS:
        settings.add_argument(flag, dest=path, default=None, **options)
    settings.add_argument(
        "--set", action="append", default=[], metavar="SECTION.KEY=VALUE",
        help="set any config value, e.g. --set eyes.open_ratio=0.8 (repeatable)",
    )
    return p.parse_args(argv)


_APP_OUTPUTS = frozenset({"app:toggle_pause"})


def _validate_actions(config: Config) -> None:
    for event, output in config.output.actions.items():
        if output.startswith("app:"):
            if output not in _APP_OUTPUTS:
                raise ValueError(
                    f"output.actions.{event}: unknown app output {output!r}; "
                    f"choose from {', '.join(sorted(_APP_OUTPUTS))}"
                )
        elif output not in OUTPUT_NAMES:
            raise ValueError(
                f"output.actions.{event}: unknown output {output!r}; "
                f"choose from {', '.join(OUTPUT_NAMES)}"
            )


def build_config(args: argparse.Namespace) -> Config:
    config = load_config(args.config)
    for _, path, _ in _SHORTCUTS:
        value = getattr(args, path)
        if value is not None:
            config = apply_overrides(config, nested(path, value))
    for item in args.set:
        config = apply_overrides(config, parse_override(item))
    _validate_actions(config)
    return config


def run(config: Config, args: argparse.Namespace) -> int:
    source = OpenCVSource(config.camera, print)
    tracker = EyeStateTracker(config.eyes)
    head = HeadTracker(config.head)
    log_rejected = print if config.feedback.log_rejected else None
    triggers = supported_triggers(create_triggers(config, log_rejected), source, print)
    last_fire_at = -1e9

    def on_fire(event: TriggerEvent, output_name: str) -> None:
        nonlocal last_fire_at
        last_fire_at = time.monotonic()
        print(f"{event.trigger}: {event.detail} -> {output_name}", flush=True)
        if config.feedback.sound:
            play_sound("trigger")

    # App-level outputs (app:*) are handled in the event loop; only keystroke
    # and mouse outputs go to ActionDispatcher.
    key_actions = {k: v for k, v in config.output.actions.items()
                   if not v.startswith("app:")}
    dispatcher = ActionDispatcher(
        create_output(config.output.dry_run),
        key_actions,
        config.output.cooldown_s,
        on_fire,
        log_rejected,
    )
    def on_pause_change(paused: bool) -> None:
        if config.feedback.sound:
            play_sound("pause" if paused else "resume")

    pause = PauseSwitch(on_pause_change)
    pause.start_global_hotkey(config.hotkeys.pause)

    log_file = args.log.open("w", newline="") if args.log else None
    log = csv.writer(log_file) if log_file else None
    if log:
        log.writerow(["t", "face", "left", "right", "combined", "baseline", "ready", "closed", "head_yaw", "head_pitch", "fired"])

    print("Running. Keep your eyes open normally for a couple of seconds to calibrate.", flush=True)
    start = time.monotonic()
    fps = 0.0
    prev = start
    try:
        while True:
            signals = source.read()
            now = signals.timestamp
            fps = 0.9 * fps + 0.1 * (1.0 / max(now - prev, 1e-6))
            prev = now

            head_yaw, head_pitch = head.update(signals)
            obs = replace(tracker.update(signals), head_yaw=head_yaw, head_pitch=head_pitch)

            fired = False
            for trigger in triggers:
                event = trigger.update(obs)
                if event is None:
                    continue
                mapped = config.output.actions.get(event.action)
                if mapped is not None and mapped.startswith("app:"):
                    print(f"{event.trigger}: {event.detail}", flush=True)
                    if mapped == "app:toggle_pause":
                        pause.toggle()
                    continue
                if pause.paused:
                    if log_rejected:
                        log_rejected(f"{event.trigger}: {event.detail} -> ignored (paused)")
                    continue
                fired = dispatcher.dispatch(event) or fired

            if log:
                log.writerow([
                    f"{now - start:.3f}", int(obs.face_present),
                    *(f"{v:.4f}" if v is not None else "" for v in
                      (obs.left, obs.right, obs.combined, obs.baseline)),
                    int(obs.ready), int(obs.closed),
                    f"{obs.head_yaw:.1f}" if obs.head_yaw is not None else "",
                    f"{obs.head_pitch:.1f}" if obs.head_pitch is not None else "", int(fired),
                ])

            if args.preview:
                key = preview.show(
                    source.debug_view(), obs, config.eyes,
                    [f"{t.name}: {t.status()}" for t in triggers],
                    pause.paused, fps, now - last_fire_at < _FLASH_S,
                )
                if key in (ord("q"), 27):
                    break
                if key == ord("p"):
                    pause.toggle()

            if args.duration is not None and now - start >= args.duration:
                break
    except KeyboardInterrupt:
        pass
    finally:
        pause.stop()
        source.close()
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
