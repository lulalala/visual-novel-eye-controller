"""Main loop: camera -> landmarks -> eye state -> triggers -> output."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import replace
from pathlib import Path

import cv2

from vn_eye import preview
from vn_eye.config import Config, load_config
from vn_eye.eyes import EyeStateTracker
from vn_eye.feedback import play_trigger_sound
from vn_eye.hotkeys import PauseSwitch
from vn_eye.landmarks import create_backend
from vn_eye.outputs import ActionDispatcher, create_output
from vn_eye.triggers import TriggerEvent, create_triggers

_FLASH_S = 0.3


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="vn-eye", description=__doc__)
    p.add_argument("-c", "--config", type=Path, help="TOML config file (see config.example.toml)")
    p.add_argument("--preview", action="store_true", help="show the camera debug window")
    p.add_argument("--dry-run", action="store_true", help="print actions instead of sending input")
    p.add_argument("--camera", type=int, help="camera index (overrides config)")
    p.add_argument("--log", type=Path, help="write per-frame eye values to a CSV file (no images)")
    p.add_argument("--duration", type=float, help="stop after this many seconds")
    return p.parse_args(argv)


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
    triggers = create_triggers(config)
    last_fire_at = -1e9

    def on_fire(event: TriggerEvent, output_name: str) -> None:
        nonlocal last_fire_at
        last_fire_at = time.monotonic()
        print(f"{event.trigger}: {event.detail} -> {output_name}", flush=True)
        if config.feedback.sound:
            play_trigger_sound()

    dispatcher = ActionDispatcher(
        create_output(config.output.dry_run),
        config.output.actions,
        config.output.cooldown_s,
        on_fire,
    )
    pause = PauseSwitch()
    pause.start_global_hotkey(config.hotkeys.pause)

    log_file = args.log.open("w", newline="") if args.log else None
    log = csv.writer(log_file) if log_file else None
    if log:
        log.writerow(["t", "face", "left", "right", "combined", "baseline", "ready", "closed", "fired"])

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
            obs = tracker.update(face)

            fired = False
            for trigger in triggers:
                event = trigger.update(obs)
                if event is not None and not pause.paused:
                    fired = dispatcher.dispatch(event) or fired

            if log:
                log.writerow([
                    f"{now - start:.3f}", int(obs.face_present),
                    *(f"{v:.4f}" if v is not None else "" for v in
                      (obs.left, obs.right, obs.combined, obs.baseline)),
                    int(obs.ready), int(obs.closed), int(fired),
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
    config = load_config(args.config)
    if args.dry_run:
        config = replace(config, output=replace(config.output, dry_run=True))
    if args.camera is not None:
        config = replace(config, camera=replace(config.camera, index=args.camera))
    return run(config, args)
