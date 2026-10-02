"""Main loop: camera -> landmarks -> eye state -> triggers -> output."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import cv2

from vn_eye import preview
from vn_eye.config import Config, apply_overrides, load_config, nested, parse_override
from vn_eye.eyes import EyeStateTracker
from vn_eye.feedback import play_sound
from vn_eye.head import HeadTracker
from vn_eye.hotkeys import PauseSwitch
from vn_eye.landmarks import create_backend
from vn_eye.outputs import OUTPUT_NAMES, ActionDispatcher, create_output
from vn_eye.triggers import TriggerEvent, create_triggers

_FLASH_S = 0.3


# Shortcut flags: (flag, config path, argparse options). Anything else can be
# set with --set SECTION.KEY=VALUE.
_SHORTCUTS: list[tuple[str, str, dict[str, Any]]] = [
    ("--camera", "camera.index", {"type": int, "metavar": "N", "help": "camera index"}),
    ("--min-duration", "long_blink.min_duration_s", {"type": float, "metavar": "S",
     "help": "shortest closure that triggers, in seconds"}),
    ("--max-duration", "long_blink.max_duration_s", {"type": float, "metavar": "S",
     "help": "longer closures are cancelled, in seconds"}),
    ("--fire-on", "long_blink.fire_on", {"choices": ["reopen", "hold"],
     "help": "fire when the eyes reopen, or as soon as --min-duration is reached"}),
    ("--output", "output.actions.next", {"choices": OUTPUT_NAMES,
     "help": "what to send to the game"}),
    ("--cooldown", "output.cooldown_s", {"type": float, "metavar": "S",
     "help": "minimum time between triggers, in seconds"}),
    ("--close-ratio", "eyes.close_ratio", {"type": float, "metavar": "R",
     "help": "closed below baseline * R (lower = needs a firmer closure)"}),
    ("--metric", "eyes.metric", {"choices": ["ear", "blendshape"], "help": "eye openness measure"}),
    ("--shake-degrees", "head_shake.amplitude_deg", {"type": float, "metavar": "DEG",
     "help": "how far to turn the head each way for the pause/resume shake"}),
    ("--no-head-shake", "head_shake.enabled", {"action": "store_const", "const": False,
     "help": "disable the head-shake pause/resume gesture"}),
    ("--dry-run", "output.dry_run", {"action": "store_const", "const": True,
     "help": "print actions instead of sending input"}),
    ("--no-sound", "feedback.sound", {"action": "store_const", "const": False,
     "help": "don't beep when triggering"}),
    ("--no-blink-log", "feedback.log_blinks", {"action": "store_const", "const": False,
     "help": "don't print closures that didn't trigger"}),
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


def build_config(args: argparse.Namespace) -> Config:
    config = load_config(args.config)
    for _, path, _ in _SHORTCUTS:
        value = getattr(args, path)
        if value is not None:
            config = apply_overrides(config, nested(path, value))
    for item in args.set:
        config = apply_overrides(config, parse_override(item))
    return config


def open_camera(config: Config) -> cv2.VideoCapture:
    cam = config.camera
    cap = cv2.VideoCapture(cam.index)
    if not cap.isOpened():
        raise SystemExit(
            f"Could not open camera {cam.index}. Check that no other app is using it "
            "and that this terminal has camera permission."
        )
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam.height)
    cap.set(cv2.CAP_PROP_FPS, cam.fps)
    return cap


def run(config: Config, args: argparse.Namespace) -> int:
    cap = open_camera(config)
    backend = create_backend(config.backend.name, config.backend.delegate)
    tracker = EyeStateTracker(config.eyes)
    head = HeadTracker(config.head)
    log_blink = print if config.feedback.log_blinks else None
    triggers = create_triggers(config, log_blink)
    last_fire_at = -1e9

    def on_fire(event: TriggerEvent, output_name: str) -> None:
        nonlocal last_fire_at
        last_fire_at = time.monotonic()
        print(f"{event.trigger}: {event.detail} -> {output_name}", flush=True)
        if config.feedback.sound:
            play_sound("trigger")

    dispatcher = ActionDispatcher(
        create_output(config.output.dry_run),
        config.output.actions,
        config.output.cooldown_s,
        on_fire,
        log_blink,
    )
    def on_pause_change(paused: bool) -> None:
        if config.feedback.sound:
            play_sound("pause" if paused else "resume")

    pause = PauseSwitch(on_pause_change)
    pause.start_global_hotkey(config.hotkeys.pause)

    log_file = args.log.open("w", newline="") if args.log else None
    log = csv.writer(log_file) if log_file else None
    if log:
        log.writerow(["t", "face", "left", "right", "combined", "baseline", "ready", "closed", "head_yaw", "fired"])

    print("Running. Keep your eyes open normally for a couple of seconds to calibrate.", flush=True)
    start = time.monotonic()
    fps = 0.0
    prev = start
    try:
        while True:
            ok, frame = cap.read()
            now = time.monotonic()
            if not ok:
                print("Camera frame grab failed", file=sys.stderr)
                time.sleep(0.1)
                continue
            fps = 0.9 * fps + 0.1 * (1.0 / max(now - prev, 1e-6))
            prev = now

            face = backend.process(frame, now)
            obs = replace(tracker.update(face), head_yaw=head.update(face))

            fired = False
            for trigger in triggers:
                event = trigger.update(obs)
                if event is None:
                    continue
                if event.action == "toggle_pause":  # works while paused, unlike outputs
                    print(f"{event.trigger}: {event.detail}", flush=True)
                    pause.toggle()
                    continue
                if pause.paused:
                    if log_blink:
                        log_blink(f"{event.trigger}: {event.detail} -> ignored (paused)")
                    continue
                fired = dispatcher.dispatch(event) or fired

            if log:
                log.writerow([
                    f"{now - start:.3f}", int(obs.face_present),
                    *(f"{v:.4f}" if v is not None else "" for v in
                      (obs.left, obs.right, obs.combined, obs.baseline)),
                    int(obs.ready), int(obs.closed),
                    f"{obs.head_yaw:.1f}" if obs.head_yaw is not None else "", int(fired),
                ])

            if args.preview:
                key = preview.show(
                    frame, face, obs, config.eyes,
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
        cap.release()
        backend.close()
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
