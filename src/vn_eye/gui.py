"""Desktop window: the live camera view with a log, and a settings window with a plot-based gesture editor."""

from __future__ import annotations

import argparse
import queue
import re
import sys
import threading
import time
import tkinter as tk
from collections import deque
from dataclasses import fields, replace
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Any, Callable

import cv2

from vn_eye import preview
from vn_eye.app import APP_OUTPUTS, FLASH_S, check_config
from vn_eye.config import SIGNALS, Config, GestureConfig, StepConfig, dump_config, load_config
from vn_eye.engine import Engine
from vn_eye.eyes import Observation
from vn_eye.outputs import OUTPUT_NAMES
from vn_eye.triggers import Replay, replay, signal_value

# Seconds of signal kept for "Live" and for saving a test recording.
RECORD_S = 4.0
_HISTORY_FRAMES = 300
_VIDEO_MAX_WIDTH = 640
_POLL_MS = 15
_LIVE_REFRESH_MS = 250

STEP_COLORS = ("#2f6fde", "#d4761c", "#2b9a66", "#b2449a", "#7656d4")
_OK = "#1d8357"
_BAD = "#bf3e2a"
_MUTED = "#5b6477"
_GRID = "#eceef3"
_ZERO = "#c9ced8"
_TRACE = "#1a2130"

# Plot ranges per signal: (min, max, grid lines, unit, value snap when dragging).
_RANGES: dict[str, tuple[float, float, tuple[float, ...], str, float]] = {
    "eyes": (0.0, 1.3, (0.0, 0.25, 0.5, 0.75, 1.0, 1.25), "", 0.01),
    "pitch": (-30.0, 30.0, (-30, -20, -10, 0, 10, 20, 30), "°", 0.5),
    "yaw": (-30.0, 30.0, (-30, -20, -10, 0, 10, 20, 30), "°", 0.5),
}
_LANE_HINTS = {
    "eyes": "Eyes: openness, 1.0 = your usual open level",
    "pitch": "Head pitch: + = tilted down",
    "yaw": "Head yaw: + = turned to your left",
}
_GESTURE_NAME = re.compile(r"[A-Za-z0-9_-]+")


def _state_text(obs: Observation, paused: bool, fps: float) -> str:
    if paused:
        state = "Paused"
    elif not obs.face_present:
        state = "No face"
    elif not obs.ready:
        state = "Calibrating…"
    else:
        state = "Eyes closed" if obs.closed else "Watching"
    return f"{state}   {fps:4.1f} fps"


class Worker:
    """Runs the engine on a background thread. Only the main thread touches
    Tk widgets; it picks up frames and log lines from here."""

    def __init__(self, config: Config) -> None:
        self.logs: queue.Queue[str] = queue.Queue()
        self.frame: tuple[bytes, str, bool] | None = None
        """The latest (PPM image, status text, paused). Replaced each frame, never queued."""
        self.engine: Engine | None = None
        self._config = config
        self._history: deque[Observation] = deque(maxlen=_HISTORY_FRAMES)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def log(self, message: str) -> None:
        self.logs.put(message)

    def _run(self) -> None:
        self.log("Starting the camera…")
        try:
            engine = Engine(self._config, self.log)
        except Exception as e:  # noqa: BLE001 - shown to the user instead of a traceback
            self.log(f"Couldn't start: {e}")
            return
        self.engine = engine
        self.log("Running. Keep your eyes open normally for a couple of seconds to calibrate.")
        try:
            while not self._stop.is_set():
                frame = engine.step()
                obs = frame.obs
                with self._lock:
                    self._history.append(obs)
                assert engine.config is not None
                img = preview.render(
                    engine.source.debug_view(), obs, engine.config.eyes, engine.statuses(),
                    engine.paused, engine.fps, obs.timestamp - engine.last_fire_at < FLASH_S,
                    hints=False,
                )
                if img.shape[1] > _VIDEO_MAX_WIDTH:
                    scale = _VIDEO_MAX_WIDTH / img.shape[1]
                    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                ppm = b"P6 %d %d 255\n" % (rgb.shape[1], rgb.shape[0]) + rgb.tobytes()
                self.frame = (ppm, _state_text(obs, engine.paused, engine.fps), engine.paused)
        except Exception as e:  # noqa: BLE001
            self.log(f"Stopped: {e}")
        finally:
            engine.close()

    def set_config(self, config: Config) -> None:
        self._config = config
        if self.engine is not None:
            self.engine.set_config(config)

    def toggle_pause(self) -> None:
        if self.engine is not None:
            self.engine.toggle_pause()

    def recent(self, seconds: float) -> list[Observation]:
        """The last ``seconds`` of observations, with time starting at 0."""
        with self._lock:
            history = list(self._history)
        if not history:
            return []
        start = max(history[-1].timestamp - seconds, history[0].timestamp)
        return [replace(o, timestamp=o.timestamp - start) for o in history if o.timestamp >= start]

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)


class MainWindow:
    """The live camera view, with the log on the side."""

    def __init__(self, root: tk.Tk, config: Config, path: Path) -> None:
        self.root = root
        self.config = config
        self.path = path
        self.settings: SettingsWindow | None = None
        self.worker = Worker(config)
        self._shown_frame: tuple[bytes, str, bool] | None = None

        root.title("vn-eye")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        bar = ttk.Frame(root, padding=(8, 6))
        bar.grid(row=0, column=0, sticky="ew")
        self.pause_button = ttk.Button(bar, text="Pause", command=self.worker.toggle_pause)
        self.pause_button.pack(side="left")
        ttk.Button(bar, text="Settings…", command=self.open_settings).pack(side="left", padx=(6, 0))
        self.practice = tk.BooleanVar(value=config.output.dry_run)
        ttk.Checkbutton(
            bar, text="Practice mode (log keys instead of sending them)",
            variable=self.practice, command=self._on_practice,
        ).pack(side="left", padx=(12, 0))
        self.status = ttk.Label(bar, text="Starting…", foreground=_MUTED)
        self.status.pack(side="right")

        body = ttk.PanedWindow(root, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.photo = tk.PhotoImage(width=640, height=480)
        video = ttk.Label(body, image=self.photo, anchor="center")
        body.add(video, weight=3)

        side = ttk.Frame(body)
        side.columnconfigure(0, weight=1)
        side.rowconfigure(1, weight=1)
        head = ttk.Frame(side)
        head.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(head, text="Log").pack(side="left")
        ttk.Button(head, text="Clear", command=self._clear_log).pack(side="right")
        self.log_text = tk.Text(side, width=52, height=24, wrap="word", state="disabled",
                                font="TkFixedFont", borderwidth=1, relief="solid")
        self.log_text.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        scroll = ttk.Scrollbar(side, orient="vertical", command=self.log_text.yview)
        scroll.grid(row=1, column=1, sticky="ns", pady=(4, 0))
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.tag_configure("fire", foreground=_OK)
        self.log_text.tag_configure("reject", foreground=_MUTED)
        self.log_text.tag_configure("time", foreground=_MUTED)
        body.add(side, weight=2)

        root.bind("p", lambda _e: self.worker.toggle_pause())
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._poll()

    def _poll(self) -> None:
        for _ in range(200):
            try:
                self._append_log(self.worker.logs.get_nowait())
            except queue.Empty:
                break
        frame = self.worker.frame
        if frame is not None and frame is not self._shown_frame:
            self._shown_frame = frame
            ppm, status, paused = frame
            self.photo.configure(data=ppm, format="ppm")
            self.status.configure(text=status)
            self.pause_button.configure(text="Resume" if paused else "Pause")
        self.root.after(_POLL_MS, self._poll)

    def _append_log(self, message: str) -> None:
        if " -> " in message and "ignored" not in message:
            tag = "fire"
        elif message.endswith(")") and "(" in message:
            tag = "reject"
        else:
            tag = ""
        at_end = self.log_text.yview()[1] > 0.999
        self.log_text.configure(state="normal")
        self.log_text.insert("end", time.strftime("%H:%M:%S  "), "time")
        self.log_text.insert("end", message + "\n", tag)
        self.log_text.configure(state="disabled")
        if at_end:
            self.log_text.see("end")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _on_practice(self) -> None:
        output = replace(self.config.output, dry_run=self.practice.get())
        self.apply_config(replace(self.config, output=output))

    def apply_config(self, config: Config) -> None:
        self.config = config
        self.practice.set(config.output.dry_run)
        self.worker.set_config(config)

    def save_config(self, config: Config) -> None:
        self.apply_config(config)
        self.path.write_text(dump_config(config), encoding="utf-8")

    def open_settings(self) -> None:
        if self.settings is not None:
            self.settings.win.lift()
            self.settings.win.focus_force()
            return
        self.settings = SettingsWindow(self)

    def close(self) -> None:
        self.worker.stop()
        self.root.destroy()


def _tint(color: str, amount: float) -> str:
    """The color mixed with white, for box fills that the trace stays readable on."""
    r, g, b = (int(color[k:k + 2], 16) for k in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(round(v + (255 - v) * amount) for v in (r, g, b))


def _fmt(value: float | None) -> str:
    return "" if value is None else f"{value:g}"


def _gesture_model(gesture: GestureConfig) -> dict[str, Any]:
    steps = []
    for s in gesture.steps:
        if s.gesture:
            above = below = None
        elif s.signal == "eyes":
            above, below = s.above_ratio, s.below_ratio
        else:
            above, below = s.above_deg, s.below_deg
        steps.append({
            "kind": "gesture" if s.gesture else s.signal, "gesture": s.gesture,
            "above": above, "below": below,
            "after_min_s": s.after_min_s, "after_max_s": s.after_max_s, "hold_s": s.hold_s,
        })
    return {
        "enabled": gesture.enabled, "output": gesture.output, "any_order": gesture.any_order,
        "within_s": gesture.within_s, "cooldown_s": gesture.cooldown_s, "steps": steps,
    }


def _gesture_config(model: dict[str, Any]) -> GestureConfig:
    steps = []
    for s in model["steps"]:
        timing = {"after_min_s": s["after_min_s"], "after_max_s": s["after_max_s"]}
        if s["kind"] == "gesture":
            steps.append(StepConfig(gesture=s["gesture"], **timing))
        else:
            unit = "ratio" if s["kind"] == "eyes" else "deg"
            steps.append(StepConfig(
                signal=s["kind"], hold_s=s["hold_s"],
                **{f"above_{unit}": s["above"], f"below_{unit}": s["below"]}, **timing,
            ))
    return GestureConfig(
        enabled=model["enabled"], steps=steps, any_order=model["any_order"],
        within_s=model["within_s"], cooldown_s=model["cooldown_s"], output=model["output"],
    )


def _new_step(kind: str) -> dict[str, Any]:
    above, below = {"eyes": (None, 0.55), "pitch": (12.0, None), "yaw": (15.0, None)}.get(kind, (None, None))
    return {"kind": kind, "gesture": "", "above": above, "below": below,
            "after_min_s": 0.0, "after_max_s": 1.0, "hold_s": 0.0}


class PlotEditor:
    """A plot of the recorded signals with one draggable box per step."""

    L, R, TOP, LANE_H, GAP, AXIS = 58, 14, 24, 150, 34, 26

    def __init__(self, parent: tk.Misc, on_drag: Callable[[int, str, float], None]) -> None:
        self.canvas = tk.Canvas(parent, width=680, height=220, background="white",
                                highlightthickness=1, highlightbackground=_ZERO)
        self._on_drag = on_drag
        self._handles: list[tuple[float, float, float, float, str, int, float | None]] = []
        self._drag: tuple[str, int, float | None, str] | None = None
        self._last: tuple[Any, ...] | None = None
        self._geo: tuple[float, float, list[str]] = (680, RECORD_S, [])
        self.canvas.bind("<Configure>", lambda _e: self._redraw())
        self.canvas.bind("<Motion>", self._hover)
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._move)
        self.canvas.bind("<ButtonRelease-1>", lambda _e: self._release())

    def draw(self, gesture: dict[str, Any], observations: list[Observation],
             result: Replay | None, duration: float) -> None:
        self._last = (gesture, observations, result, duration)
        self._redraw()

    def _redraw(self) -> None:
        if self._last is None:
            return
        gesture, observations, result, duration = self._last
        c = self.canvas
        c.delete("all")
        self._handles = []
        lanes = list(dict.fromkeys(s["kind"] for s in gesture["steps"] if s["kind"] in SIGNALS))
        height = self.TOP + max(len(lanes), 1) * self.LANE_H + max(len(lanes) - 1, 0) * self.GAP + self.AXIS
        if int(c.cget("height")) != height:
            c.configure(height=height)
        width = max(c.winfo_width(), 400)
        if not lanes:
            c.create_text(width / 2, height / 2, fill=_MUTED, text=(
                "This gesture's steps are other gestures, so there is nothing to plot.\n"
                "Test it with the recordings on the right."), justify="center")
            return
        self._geo = (width, duration, lanes)

        def x(t: float) -> float:
            return self.L + max(0.0, min(duration, t)) / duration * (width - self.L - self.R)

        def lane_top(li: int) -> float:
            return self.TOP + li * (self.LANE_H + self.GAP)

        def y(v: float, li: int) -> float:
            lo, hi = _RANGES[lanes[li]][:2]
            v = max(lo, min(hi, v))
            return lane_top(li) + (1 - (v - lo) / (hi - lo)) * self.LANE_H

        bottom = height - self.AXIS
        tick = 0.5
        t = 0.0
        while t <= duration + 1e-9:
            c.create_line(x(t), self.TOP, x(t), bottom, fill=_GRID)
            c.create_text(x(t), bottom + 13, text=f"{t:g} s", fill=_MUTED, font="TkSmallCaptionFont")
            t += tick
        for li, sig in enumerate(lanes):
            lo, hi, grid, unit, _ = _RANGES[sig]
            c.create_text(self.L, lane_top(li) - 10, anchor="w", text=_LANE_HINTS[sig], fill=_MUTED,
                          font="TkSmallCaptionFont")
            for v in grid:
                zero = (v == 0 and sig != "eyes") or (v == 1.0 and sig == "eyes")
                c.create_line(self.L, y(v, li), width - self.R, y(v, li), fill=_ZERO if zero else _GRID)
                label = f"{v:.2f}" if sig == "eyes" else f"{v:g}{unit}"
                c.create_text(self.L - 6, y(v, li), anchor="e", text=label, fill=_MUTED, font="TkSmallCaptionFont")

        # Each step's box. A box after the first starts at the moment the
        # previous step was reached, so its edges are the allowed time after it.
        reached = dict(result.steps) if result else {}
        order = [i for i, _ in sorted(reached.items(), key=lambda kv: kv[1])]
        steps = gesture["steps"]
        for i, step in enumerate(steps):
            if step["kind"] not in SIGNALS:
                continue
            li = lanes.index(step["kind"])
            color = STEP_COLORS[i % len(STEP_COLORS)]
            # prev: when the step before this one was reached. A box without
            # one can be entered at any time (a first step), or is dashed
            # when its place in the attempt isn't known yet.
            prev: float | None = None
            anchored = True
            if i in reached:
                k = order.index(i)
                prev = reached[order[k - 1]] if k > 0 else None
            elif order and (gesture["any_order"] or i == len(order)):
                prev = reached[order[-1]]
            elif order or (i > 0 and not gesture["any_order"]):
                anchored = False
            t0, t1 = 0.0, duration
            if prev is not None:
                t0 = prev + step["after_min_s"]
                t1 = prev + step["after_max_s"] if step["after_max_s"] else duration
            y_top = y(step["below"], li) if step["below"] is not None else lane_top(li)
            y_bot = y(step["above"], li) if step["above"] is not None else lane_top(li) + self.LANE_H
            bx, bw = x(t0), max(2.0, x(t1) - x(t0))
            c.create_rectangle(bx, y_top, bx + bw, y_bot, outline=color, width=1,
                               dash="" if anchored else (4, 3), fill=_tint(color, 0.86 if anchored else 0.94))
            c.create_rectangle(bx + 3, y_top + 3, bx + 19, y_top + 19, fill=color, outline="")
            c.create_text(bx + 11, y_top + 11, text=str(i + 1), fill="white", font="TkSmallCaptionFont")
            unit = _RANGES[step["kind"]][3]
            if step["above"] is not None:
                self._edge(bx, y_bot, bx + bw, y_bot, color, "above", i, None)
                c.create_text(bx + bw - 4, y_bot + 9, anchor="e", fill=color, font="TkSmallCaptionFont",
                              text=f"{step['above']:g}{unit}")
            if step["below"] is not None:
                self._edge(bx, y_top, bx + bw, y_top, color, "below", i, None)
                c.create_text(bx + bw - 4, y_top - 9, anchor="e", fill=color, font="TkSmallCaptionFont",
                              text=f"{step['below']:g}{unit}")
            if prev is not None:
                self._edge(bx, y_top + 4, bx, y_bot - 4, color, "after_min_s", i, prev)
                if step["after_max_s"]:
                    self._edge(x(t1), y_top + 4, x(t1), y_bot - 4, color, "after_max_s", i, prev)
                    c.create_text(x(t1) + 4, y_bot - 10, anchor="w", fill=color, font="TkSmallCaptionFont",
                                  text=f"≤{step['after_max_s']:.2f}s")

        for li, sig in enumerate(lanes):
            points: list[float] = []
            for o in observations:
                v = signal_value(sig, o)
                if v is None:
                    if len(points) >= 4:
                        c.create_line(*points, fill=_TRACE, width=2)
                    points = []
                    continue
                points += [x(o.timestamp), y(v, li)]
            if len(points) >= 4:
                c.create_line(*points, fill=_TRACE, width=2)

        for i, t in reached.items():
            step = steps[i]
            if step["kind"] not in SIGNALS or not observations:
                continue
            o = min(observations, key=lambda o: abs(o.timestamp - t))
            v = signal_value(step["kind"], o)
            if v is not None:
                li = lanes.index(step["kind"])
                c.create_oval(x(t) - 5, y(v, li) - 5, x(t) + 5, y(v, li) + 5,
                              fill=STEP_COLORS[i % len(STEP_COLORS)], outline="white", width=2)
        if result is not None and result.fired_at is not None:
            fx = x(result.fired_at)
            c.create_line(fx, self.TOP, fx, bottom, fill=_OK, dash=(4, 3), width=2)
            left = fx > width - 90
            c.create_text(fx - 4 if left else fx + 4, bottom - 4, anchor="se" if left else "sw", fill=_OK,
                          text=f"fires {result.fired_at:.2f}s", font="TkSmallCaptionFont")
        if not observations:
            c.create_text(width / 2, self.TOP + 40, fill=_MUTED, text="No signal yet. Is the camera running?")

    def _edge(self, x1: float, y1: float, x2: float, y2: float, color: str,
              kind: str, step: int, prev: float | None) -> None:
        self.canvas.create_line(x1, y1, x2, y2, fill=color, width=3)
        pad = 6
        self._handles.append((min(x1, x2) - pad, min(y1, y2) - pad, max(x1, x2) + pad, max(y1, y2) + pad,
                              kind, step, prev))

    def _hit(self, event: tk.Event) -> tuple[str, int, float | None] | None:
        for x1, y1, x2, y2, kind, step, prev in reversed(self._handles):
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                return kind, step, prev
        return None

    def _hover(self, event: tk.Event) -> None:
        hit = self._hit(event)
        if hit is None:
            self.canvas.configure(cursor="")
        else:
            self.canvas.configure(cursor="sb_h_double_arrow" if hit[0].startswith("after") else "sb_v_double_arrow")

    def _press(self, event: tk.Event) -> None:
        hit = self._hit(event)
        if hit is not None and self._last is not None:
            kind, step, prev = hit
            self._drag = (kind, step, prev, self._last[0]["steps"][step]["kind"])

    def _move(self, event: tk.Event) -> None:
        if self._drag is None:
            return
        kind, step, prev, signal = self._drag
        width, duration, lanes = self._geo
        if kind in ("above", "below"):
            li = lanes.index(signal)
            lo, hi, _, _, snap = _RANGES[signal]
            top = self.TOP + li * (self.LANE_H + self.GAP)
            v = lo + (1 - (event.y - top) / self.LANE_H) * (hi - lo)
            v = round(max(lo, min(hi, v)) / snap) * snap
            self._on_drag(step, kind, round(v, 2))
        elif prev is not None:
            t = (event.x - self.L) / (width - self.L - self.R) * duration
            self._on_drag(step, kind, max(0.0, round(t - prev, 2)))

    def _release(self) -> None:
        self._drag = None


def _result_text(result: Replay | None) -> tuple[str, str]:
    """(text, tag) for a recording's row in the test list."""
    if result is None:
        return "–", ""
    if result.fired_at is not None:
        return f"✓ {result.reason}", "ok"
    return f"✕ {result.reason}", "bad"


class SettingsWindow:
    """Gestures (plot, steps, test recordings) and general settings, in their own window."""

    def __init__(self, app: MainWindow) -> None:
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title("vn-eye settings")
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.builtin = set(Config().gestures)
        self.tests: list[tuple[str, list[Observation]]] = []
        self.recording = "live"
        self._suppress = False
        self._field_errors: dict[str, str] = {}
        self._load(app.config)

        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(0, weight=1)
        notebook = ttk.Notebook(self.win)
        notebook.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        gestures_tab = ttk.Frame(notebook, padding=8)
        general_tab = ttk.Frame(notebook, padding=12)
        notebook.add(gestures_tab, text="Gestures")
        notebook.add(general_tab, text="General")
        self._build_gestures_tab(gestures_tab)
        self._build_general_tab(general_tab)

        bottom = ttk.Frame(self.win, padding=(8, 0, 8, 8))
        bottom.grid(row=1, column=0, sticky="ew")
        self.message = ttk.Label(bottom, text="", foreground=_BAD, wraplength=640)
        self.message.pack(side="left", fill="x", expand=True)
        self.save_button = ttk.Button(bottom, text="Save", command=self.save)
        self.save_button.pack(side="right")
        self.apply_button = ttk.Button(bottom, text="Apply", command=self.apply)
        self.apply_button.pack(side="right", padx=6)
        ttk.Button(bottom, text="Revert", command=self.revert).pack(side="right")

        self._select(next(iter(self.gestures)))
        self._live_loop()

    # Model

    def _load(self, config: Config) -> None:
        self.gestures = {name: _gesture_model(g) for name, g in config.gestures.items()}
        self.general = {
            section: {f.name: getattr(getattr(config, section), f.name) for f in fields(getattr(config, section))}
            for section in ("camera", "eyes", "head", "feedback")
        }

    def build_config(self) -> Config:
        """The edited settings; raises ValueError if they aren't valid."""
        if self._field_errors:
            raise ValueError(next(iter(self._field_errors.values())))
        base = self.app.config
        sections = {s: replace(getattr(base, s), **values) for s, values in self.general.items()}
        gestures = {name: _gesture_config(m) for name, m in self.gestures.items()}
        config = replace(base, gestures=gestures, **sections)
        check_config(config)
        return config

    # Gestures tab

    def _build_gestures_tab(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(1, weight=1)

        left = ttk.Frame(tab)
        left.grid(row=0, column=0, rowspan=4, sticky="ns", padx=(0, 10))
        ttk.Label(left, text="Gestures").pack(anchor="w")
        self.gesture_list = tk.Listbox(left, height=12, width=20, exportselection=False, activestyle="none")
        self.gesture_list.pack(fill="y", expand=True, pady=(4, 6))
        self.gesture_list.bind("<<ListboxSelect>>", self._on_list_select)
        ttk.Button(left, text="New gesture…", command=self._new_gesture).pack(fill="x")
        self.delete_button = ttk.Button(left, text="Delete", command=self._delete_gesture)
        self.delete_button.pack(fill="x", pady=(4, 0))
        self.reset_button = ttk.Button(left, text="Reset to default", command=self._reset_gesture)
        self.reset_button.pack(fill="x", pady=(4, 0))

        top = ttk.Frame(tab)
        top.grid(row=0, column=1, sticky="ew")
        self.enabled = tk.BooleanVar()
        ttk.Checkbutton(top, text="Enabled", variable=self.enabled, command=self._on_gesture_field).pack(side="left")
        ttk.Label(top, text="Output").pack(side="left", padx=(14, 4))
        self.output = ttk.Combobox(top, state="readonly", width=18,
                                   values=["(none)", *OUTPUT_NAMES, *sorted(APP_OUTPUTS)])
        self.output.bind("<<ComboboxSelected>>", lambda _e: self._on_gesture_field())
        self.output.pack(side="left")
        self.any_order = tk.BooleanVar()
        ttk.Checkbutton(top, text="Steps in any order", variable=self.any_order,
                        command=self._on_gesture_field).pack(side="left", padx=(14, 0))
        self.gesture_vars: dict[str, tk.StringVar] = {}
        for key, label in (("within_s", "Within"), ("cooldown_s", "Cooldown")):
            ttk.Label(top, text=label).pack(side="left", padx=(14, 4))
            var = tk.StringVar()
            var.trace_add("write", lambda *_a, k=key: self._on_gesture_number(k))
            ttk.Entry(top, textvariable=var, width=6).pack(side="left")
            ttk.Label(top, text="s").pack(side="left", padx=(2, 0))
            self.gesture_vars[key] = var

        middle = ttk.Frame(tab)
        middle.grid(row=1, column=1, sticky="nsew", pady=(8, 0))
        middle.columnconfigure(0, weight=1)
        middle.rowconfigure(1, weight=1)
        self.result = ttk.Label(middle, text="", font="TkHeadingFont")
        self.result.grid(row=0, column=0, sticky="w")
        self.plot = PlotEditor(middle, self._on_drag)
        self.plot.canvas.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        ttk.Label(middle, foreground=_MUTED, text=(
            "Drag a box edge to change a threshold or a time limit. Boxes after step 1 start when "
            "the previous step was reached in this recording.")).grid(row=2, column=0, sticky="w", pady=(4, 0))

        self.steps_frame = ttk.Frame(tab)
        self.steps_frame.grid(row=2, column=1, sticky="ew", pady=(8, 0))
        buttons = ttk.Frame(tab)
        buttons.grid(row=3, column=1, sticky="w", pady=(6, 0))
        ttk.Button(buttons, text="+ Add step", command=self._add_step).pack(side="left")
        ttk.Label(buttons, foreground=_MUTED, text="Leave a number empty for no limit.").pack(side="left", padx=10)

        right = ttk.Frame(tab)
        right.grid(row=0, column=2, rowspan=4, sticky="ns", padx=(10, 0))
        ttk.Label(right, text="Test against recordings").pack(anchor="w")
        self.tests_view = ttk.Treeview(right, columns=("result",), show="tree headings", height=10,
                                       selectmode="browse")
        self.tests_view.heading("#0", text="Recording")
        self.tests_view.heading("result", text="Result")
        self.tests_view.column("#0", width=150)
        self.tests_view.column("result", width=260)
        self.tests_view.tag_configure("ok", foreground=_OK)
        self.tests_view.tag_configure("bad", foreground=_BAD)
        self.tests_view.pack(fill="y", expand=True, pady=(4, 6))
        self.tests_view.bind("<<TreeviewSelect>>", self._on_test_select)
        ttk.Button(right, text=f"Save last {RECORD_S:g} s as a test", command=self._save_test).pack(fill="x")
        ttk.Button(right, text="Remove test", command=self._remove_test).pack(fill="x", pady=(4, 0))
        ttk.Label(right, foreground=_MUTED, wraplength=410, justify="left", text=(
            "Do the gesture, then save the last few seconds. Tests keep only the eye and head "
            "numbers, in memory, never images.")).pack(anchor="w", pady=(6, 0))

    def _refresh_list(self) -> None:
        self.gesture_list.delete(0, "end")
        for name, m in self.gestures.items():
            self.gesture_list.insert("end", name if m["enabled"] else f"{name} (off)")
        names = list(self.gestures)
        if self.current in names:
            index = names.index(self.current)
            self.gesture_list.selection_clear(0, "end")
            self.gesture_list.selection_set(index)

    def _select(self, name: str) -> None:
        self.current = name
        m = self.gestures[name]
        self._suppress = True
        self.enabled.set(m["enabled"])
        self.output.set(m["output"] or "(none)")
        self.any_order.set(m["any_order"])
        for key, var in self.gesture_vars.items():
            var.set(_fmt(m[key]))
        self._suppress = False
        self.delete_button.configure(state="disabled" if name in self.builtin else "normal")
        self.reset_button.configure(state="normal" if name in self.builtin else "disabled")
        self._field_errors = {}
        self._refresh_list()
        self._build_steps()
        self._refresh()

    def _on_list_select(self, _event: tk.Event) -> None:
        sel = self.gesture_list.curselection()
        if sel:
            self._select(list(self.gestures)[sel[0]])

    def _on_gesture_field(self) -> None:
        if self._suppress:
            return
        m = self.gestures[self.current]
        m["enabled"] = self.enabled.get()
        m["output"] = "" if self.output.get() == "(none)" else self.output.get()
        if m["any_order"] != self.any_order.get():
            m["any_order"] = self.any_order.get()
            self._build_steps()
        self._refresh_list()
        self._refresh()

    def _on_gesture_number(self, key: str) -> None:
        if self._suppress:
            return
        self._set_number(self.gestures[self.current], key, self.gesture_vars[key].get(), key, optional=False)
        self._refresh()

    def _set_number(self, target: dict[str, Any], key: str, text: str, label: str, optional: bool) -> None:
        text = text.strip()
        try:
            value = None if text == "" and optional else float(text or 0)
        except ValueError:
            self._field_errors[label] = f"{label}: {text!r} is not a number"
            return
        self._field_errors.pop(label, None)
        target[key] = value

    def _new_gesture(self) -> None:
        name = simpledialog.askstring("New gesture", "Name (letters, digits, _ and -):", parent=self.win)
        if not name:
            return
        if not _GESTURE_NAME.fullmatch(name) or name in self.gestures:
            messagebox.showerror("New gesture", f"{name!r} is taken or has other characters than "
                                 "letters, digits, _ and -.", parent=self.win)
            return
        self.gestures[name] = {"enabled": True, "output": "", "any_order": False, "within_s": 0.0,
                               "cooldown_s": 1.0, "steps": [{**_new_step("eyes"), "after_max_s": 0.0}]}
        self._select(name)

    def _delete_gesture(self) -> None:
        if self.current in self.builtin:
            return
        if messagebox.askyesno("Delete gesture", f"Delete {self.current}?", parent=self.win):
            del self.gestures[self.current]
            self._select(next(iter(self.gestures)))

    def _reset_gesture(self) -> None:
        if self.current in self.builtin:
            self.gestures[self.current] = _gesture_model(Config().gestures[self.current])
            self._select(self.current)

    # Steps table

    def _build_steps(self) -> None:
        frame = self.steps_frame
        for child in frame.winfo_children():
            child.destroy()
        self.step_vars: dict[tuple[int, str], tk.StringVar] = {}
        headers = ("", "Signal", "Above", "", "Below", "", "After previous: min", "max", "Hold", "")
        for col, text in enumerate(headers):
            ttk.Label(frame, text=text, foreground=_MUTED).grid(row=0, column=col, sticky="w", padx=3)
        m = self.gestures[self.current]
        kinds = [*SIGNALS, *(f"gesture: {n}" for n in self.gestures if n != self.current)]
        for i, step in enumerate(m["steps"]):
            r = i + 1
            color = STEP_COLORS[i % len(STEP_COLORS)]
            tk.Label(frame, text=str(i + 1), background=color, foreground="white", width=2).grid(
                row=r, column=0, padx=3, pady=2)
            kind = ttk.Combobox(frame, state="readonly", width=18, values=kinds)
            kind.set(f"gesture: {step['gesture']}" if step["kind"] == "gesture" else step["kind"])
            kind.bind("<<ComboboxSelected>>", lambda _e, i=i, w=kind: self._on_kind(i, w.get()))
            kind.grid(row=r, column=1, padx=3)
            is_signal = step["kind"] in SIGNALS
            unit = _RANGES[step["kind"]][3] if is_signal else ""
            first = i == 0 and not m["any_order"]
            cells = (("above", 2, True, is_signal), ("below", 4, True, is_signal),
                     ("after_min_s", 6, False, not first), ("after_max_s", 7, False, not first),
                     ("hold_s", 8, False, is_signal))
            for key, col, optional, enabled in cells:
                var = tk.StringVar(value=_fmt(step[key]))
                var.trace_add("write", lambda *_a, i=i, k=key, opt=optional: self._on_step_number(i, k, opt))
                entry = ttk.Entry(frame, textvariable=var, width=7, state="normal" if enabled else "disabled")
                entry.grid(row=r, column=col, padx=3)
                self.step_vars[(i, key)] = var
            ttk.Label(frame, text=unit).grid(row=r, column=3, sticky="w")
            ttk.Label(frame, text=unit).grid(row=r, column=5, sticky="w")
            ttk.Button(frame, text="✕", width=3, command=lambda i=i: self._delete_step(i),
                       state="normal" if len(m["steps"]) > 1 else "disabled").grid(row=r, column=9, padx=3)

    def _on_kind(self, i: int, value: str) -> None:
        steps = self.gestures[self.current]["steps"]
        old = steps[i]
        if value.startswith("gesture: "):
            new = {**_new_step("gesture"), "gesture": value.removeprefix("gesture: ")}
        else:
            new = _new_step(value)
        new["after_min_s"], new["after_max_s"] = old["after_min_s"], old["after_max_s"]
        steps[i] = new
        self._build_steps()
        self._refresh()

    def _on_step_number(self, i: int, key: str, optional: bool) -> None:
        if self._suppress:
            return
        step = self.gestures[self.current]["steps"][i]
        self._set_number(step, key, self.step_vars[(i, key)].get(), f"Step {i + 1} {key}", optional)
        self._refresh()

    def _add_step(self) -> None:
        steps = self.gestures[self.current]["steps"]
        kind = steps[-1]["kind"] if steps else "eyes"
        steps.append(_new_step(kind if kind in SIGNALS else "eyes"))
        self._build_steps()
        self._refresh()

    def _delete_step(self, i: int) -> None:
        steps = self.gestures[self.current]["steps"]
        if len(steps) > 1:
            del steps[i]
            self._field_errors = {}
            self._build_steps()
            self._refresh()

    def _on_drag(self, i: int, key: str, value: float) -> None:
        step = self.gestures[self.current]["steps"][i]
        gap = _RANGES[step["kind"]][4] * 2
        if key == "above" and step["below"] is not None:
            value = min(value, step["below"] - gap)
        if key == "below" and step["above"] is not None:
            value = max(value, step["above"] + gap)
        if key == "after_min_s" and step["after_max_s"]:
            value = min(value, step["after_max_s"])
        if key == "after_max_s":
            value = max(value, step["after_min_s"], 0.01)
        value = round(value, 2)
        if step[key] == value:
            return
        step[key] = value
        self._suppress = True
        self.step_vars[(i, key)].set(_fmt(value))
        self._suppress = False
        self._refresh()

    # Recordings

    def _observations(self) -> list[Observation]:
        if self.recording == "live":
            return self.app.worker.recent(RECORD_S)
        return self.tests[int(self.recording)][1]

    def _replay(self, config: Config | None, observations: list[Observation]) -> Replay | None:
        if config is None or not observations:
            return None
        try:
            return replay(config, self.current, observations)
        except ValueError:
            return None

    def _refresh(self) -> None:
        """Validates the edits, then re-runs the gesture on every recording and redraws."""
        try:
            config: Config | None = self.build_config()
            self.message.configure(text="")
            state = "normal"
        except ValueError as e:
            config = None
            self.message.configure(text=str(e), foreground=_BAD)
            state = "disabled"
        self.apply_button.configure(state=state)
        self.save_button.configure(state=state)

        view = self.tests_view
        selected = self.recording
        view.delete(*view.get_children())
        rows = [("live", f"Live (last {RECORD_S:g} s)", self.app.worker.recent(RECORD_S))]
        rows += [(str(k), name, obs) for k, (name, obs) in enumerate(self.tests)]
        for iid, name, obs in rows:
            text, tag = _result_text(self._replay(config, obs))
            view.insert("", "end", iid=iid, text=name, values=(text,), tags=(tag,))
        if selected not in view.get_children():
            selected = "live"
        self.recording = selected
        view.selection_set(selected)
        self._draw_plot(config)

    def _draw_plot(self, config: Config | None) -> None:
        observations = self._observations()
        result = self._replay(config, observations)
        if result is None:
            self.result.configure(text="", foreground=_MUTED)
        elif result.fired_at is not None:
            self.result.configure(text=f"✓ Fires at {result.fired_at:.2f}s", foreground=_OK)
        else:
            self.result.configure(text=f"✕ {result.reason[:1].upper()}{result.reason[1:]}", foreground=_BAD)
        self.plot.draw(self.gestures[self.current], observations, result, RECORD_S)

    def _on_test_select(self, _event: tk.Event) -> None:
        sel = self.tests_view.selection()
        if sel and sel[0] != self.recording:
            self.recording = sel[0]
            self._refresh()

    def _save_test(self) -> None:
        observations = self.app.worker.recent(RECORD_S)
        if not observations:
            return
        self.tests.append((f"Test {len(self.tests) + 1} ({time.strftime('%H:%M:%S')})", observations))
        self.recording = str(len(self.tests) - 1)
        self._refresh()

    def _remove_test(self) -> None:
        if self.recording != "live":
            del self.tests[int(self.recording)]
            self.recording = "live"
            self._refresh()

    def _live_loop(self) -> None:
        if not self.win.winfo_exists():
            return
        try:
            config: Config | None = self.build_config()
        except ValueError:
            config = None
        text, tag = _result_text(self._replay(config, self.app.worker.recent(RECORD_S)))
        if self.tests_view.exists("live"):
            self.tests_view.item("live", values=(text,), tags=(tag,))
        if self.recording == "live":
            self._draw_plot(config)
        self.win.after(_LIVE_REFRESH_MS, self._live_loop)

    # General tab

    def _build_general_tab(self, tab: ttk.Frame) -> None:
        ttk.Label(tab, foreground=_MUTED, wraplength=640, justify="left", text=(
            "Changing camera settings reopens the camera. Changing eyes or head settings makes "
            "vn-eye learn your usual eye openness and head position again.")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        self.general_vars: list[Any] = []
        row = 1
        for section, values in self.general.items():
            ttk.Label(tab, text=section.capitalize(), font="TkHeadingFont").grid(
                row=row, column=0, sticky="w", pady=(8, 2))
            row += 1
            for key, value in values.items():
                ttk.Label(tab, text=key).grid(row=row, column=0, sticky="w", padx=(12, 8))
                if isinstance(value, bool):
                    bvar = tk.BooleanVar(value=value)
                    ttk.Checkbutton(tab, variable=bvar, command=lambda s=section, k=key, v=bvar: self._on_general_bool(
                        s, k, v.get())).grid(row=row, column=1, sticky="w")
                    self.general_vars.append(bvar)
                else:
                    svar = tk.StringVar(value=_fmt(value) if isinstance(value, float) else str(value))
                    svar.trace_add("write", lambda *_a, s=section, k=key, v=svar, t=type(value): self._on_general_text(
                        s, k, v.get(), t))
                    ttk.Entry(tab, textvariable=svar, width=10).grid(row=row, column=1, sticky="w")
                    self.general_vars.append(svar)
                row += 1

    def _on_general_bool(self, section: str, key: str, value: bool) -> None:
        self.general[section][key] = value
        self._refresh()

    def _on_general_text(self, section: str, key: str, text: str, kind: type) -> None:
        label = f"{section}.{key}"
        try:
            self.general[section][key] = kind(text.strip())
            self._field_errors.pop(label, None)
        except ValueError:
            self._field_errors[label] = f"{label}: {text!r} is not a{'n integer' if kind is int else ' number'}"
        self._refresh()

    # Buttons

    def apply(self) -> None:
        try:
            config = self.build_config()
        except ValueError as e:
            self.message.configure(text=str(e), foreground=_BAD)
            return
        self.app.apply_config(config)
        self.message.configure(text="Applied. Not saved yet.", foreground=_MUTED)

    def save(self) -> None:
        try:
            config = self.build_config()
            self.app.save_config(config)
        except (ValueError, OSError) as e:
            self.message.configure(text=str(e), foreground=_BAD)
            return
        self.message.configure(text=f"Applied and saved to {self.app.path}.", foreground=_MUTED)

    def revert(self) -> None:
        self._load(self.app.config)
        self._field_errors = {}
        name = self.current if self.current in self.gestures else next(iter(self.gestures))
        for child in self.win.winfo_children():
            if isinstance(child, ttk.Notebook):
                general = child.nametowidget(child.tabs()[1])
                for widget in general.winfo_children():
                    widget.destroy()
                self._build_general_tab(general)
        self._select(name)
        self.message.configure(text="Reverted to the settings in use.", foreground=_MUTED)

    def close(self) -> None:
        self.app.settings = None
        self.win.destroy()


def _windows_sharp_text() -> None:
    """Without this, Windows scales the window up as a bitmap on high-DPI screens, so text looks blurry."""
    if sys.platform == "win32":
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vn-eye-gui", description="vn-eye with a window: live view, log and settings.")
    p.add_argument("-c", "--config", type=Path, default=Path("config.toml"),
                   help="config file to load and save (default: config.toml, created on first save)")
    args = p.parse_args(argv)
    _windows_sharp_text()
    root = tk.Tk()
    try:
        config = load_config(args.config) if args.config.exists() else Config()
        check_config(config)
    except (ValueError, OSError) as e:
        root.withdraw()
        messagebox.showerror("vn-eye", f"Can't load {args.config}:\n\n{e}")
        root.destroy()
        return 2
    MainWindow(root, config, args.config)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
