"""Desktop window: the log, an optional camera view, and a settings window with a plot-based gesture editor."""

from __future__ import annotations

import argparse
import math
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
from vn_eye.tuning import DO, KIND_LABELS, Fit, Take, can_tune, fit, suggestions, trim

# Seconds of signal kept for "Live" and for saving a test recording.
RECORD_S = 4.0
_HISTORY_FRAMES = 900
_VIDEO_MAX_WIDTH = 640
_POLL_MS = 15
_LIVE_REFRESH_MS = 250
# A wizard take stops by itself after this long; the history keeps a bit more.
MAX_TAKE_S = 20.0

STEP_COLORS = ("#2f6fde", "#d4761c", "#2b9a66", "#b2449a", "#7656d4")
_OK = "#1d8357"
_BAD = "#bf3e2a"
_MUTED = "#5b6477"
_GRID = "#eceef3"
_ZERO = "#c9ced8"
_TRACE = "#1a2130"
_GRID_TRACE = "#b4bac7"

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
        self.status: tuple[str, bool] | None = None
        """The latest (status text, paused). Replaced each frame, never queued."""
        self.frame: bytes | None = None
        """The latest camera view as a PPM image, while show_view is set."""
        self.show_view = threading.Event()
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
                self.status = (_state_text(obs, engine.paused, engine.fps), engine.paused)
                if not self.show_view.is_set():
                    # Drawing and converting the view costs CPU on every frame.
                    continue
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
                self.frame = b"P6 %d %d 255\n" % (rgb.shape[1], rgb.shape[0]) + rgb.tobytes()
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


class CameraWindow:
    """The live camera view. The worker only draws it while this window is open."""

    def __init__(self, app: MainWindow) -> None:
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title("vn-eye camera view")
        self.photo = tk.PhotoImage(width=640, height=480)
        ttk.Label(self.win, image=self.photo, anchor="center").pack(fill="both", expand=True)
        self.win.bind("p", lambda _e: app.worker.toggle_pause())
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self._shown: bytes | None = None
        app.worker.show_view.set()

    def show(self, frame: bytes | None) -> None:
        if frame is not None and frame is not self._shown:
            self._shown = frame
            self.photo.configure(data=frame, format="ppm")

    def close(self) -> None:
        self.app.worker.show_view.clear()
        self.app.worker.frame = None
        self.app.camera = None
        self.win.destroy()


class MainWindow:
    """The log, with buttons for pause, the camera view, settings and the wizard."""

    def __init__(self, root: tk.Tk, config: Config, path: Path) -> None:
        self.root = root
        self.config = config
        self.path = path
        self.settings: SettingsWindow | None = None
        self.wizard: WizardWindow | None = None
        self.camera: CameraWindow | None = None
        self.worker = Worker(config)
        self._shown_status: tuple[str, bool] | None = None

        root.title("vn-eye")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        bar = ttk.Frame(root, padding=(8, 6))
        bar.grid(row=0, column=0, sticky="ew")
        self.pause_button = ttk.Button(bar, text="Pause", command=self.worker.toggle_pause)
        self.pause_button.pack(side="left")
        ttk.Button(bar, text="Camera view…", command=self.open_camera).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Settings…", command=self.open_settings).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Gesture wizard…", command=self.open_wizard).pack(side="left", padx=(6, 0))
        self.status = ttk.Label(bar, text="Starting…", foreground=_MUTED)
        self.status.pack(side="right")

        side = ttk.Frame(root)
        side.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        side.columnconfigure(0, weight=1)
        side.rowconfigure(1, weight=1)
        head = ttk.Frame(side)
        head.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(head, text="Log").pack(side="left")
        ttk.Button(head, text="Clear", command=self._clear_log).pack(side="right")
        self.log_text = tk.Text(side, width=90, height=24, wrap="word", state="disabled",
                                font="TkFixedFont", borderwidth=1, relief="solid")
        self.log_text.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        scroll = ttk.Scrollbar(side, orient="vertical", command=self.log_text.yview)
        scroll.grid(row=1, column=1, sticky="ns", pady=(4, 0))
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.tag_configure("fire", foreground=_OK)
        self.log_text.tag_configure("reject", foreground=_MUTED)
        self.log_text.tag_configure("time", foreground=_MUTED)

        root.bind("p", lambda _e: self.worker.toggle_pause())
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._poll()

    def _poll(self) -> None:
        for _ in range(200):
            try:
                self._append_log(self.worker.logs.get_nowait())
            except queue.Empty:
                break
        status = self.worker.status
        if status is not None and status != self._shown_status:
            self._shown_status = status
            text, paused = status
            self.status.configure(text=text)
            self.pause_button.configure(text="Resume" if paused else "Pause")
        if self.camera is not None:
            self.camera.show(self.worker.frame)
        self.root.after(_POLL_MS, self._poll)

    def _append_log(self, message: str) -> None:
        if " -> " in message and "not sent" not in message:
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

    def apply_config(self, config: Config) -> None:
        self.config = config
        self.worker.set_config(config)

    def save_config(self, config: Config) -> None:
        self.apply_config(config)
        self.path.write_text(dump_config(config), encoding="utf-8")

    def open_camera(self) -> None:
        if self.camera is not None:
            self.camera.win.lift()
            self.camera.win.focus_force()
            return
        self.camera = CameraWindow(self)

    def open_settings(self) -> None:
        if self.settings is not None:
            self.settings.win.lift()
            self.settings.win.focus_force()
            return
        self.settings = SettingsWindow(self)

    def open_wizard(self, settings: SettingsWindow | None = None) -> None:
        """From the settings window, the wizard starts from its edits and hands
        the result back to it; otherwise it uses and applies the settings in use."""
        if self.wizard is not None:
            self.wizard.win.lift()
            return
        name = settings.current if settings is not None else next(iter(self.config.gestures))
        self.wizard = WizardWindow(self, settings, name)

    def use_fit(self, name: str, gesture: GestureConfig, takes: list[Take]) -> None:
        """Applies the wizard's result and offers to save."""
        config = replace(self.config, gestures={**self.config.gestures, name: gesture})
        check_config(config)
        self.apply_config(config)
        self.worker.log(f"{name}: wizard settings applied")
        if self.settings is not None:
            # Other unapplied edits in the open settings window stay as they are.
            self.settings.gestures[name] = _gesture_model(gesture)
            self.settings._select(name)
        if messagebox.askyesno("Gesture wizard", f"{name} is using the new settings.\n\n"
                               f"Save them to {self.path}?", parent=self.root):
            try:
                self.save_config(config)
                self.worker.log(f"Saved to {self.path}")
            except OSError as e:
                messagebox.showerror("Gesture wizard", f"Couldn't save {self.path}:\n\n{e}", parent=self.root)

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
    guards = [{"kind": g.signal, "above": g.above_deg, "below": g.below_deg} for g in gesture.guards]
    return {
        "guards": guards,
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
    guards = [StepConfig(signal=g["kind"], above_deg=g["above"], below_deg=g["below"])
              for g in model["guards"]]
    return GestureConfig(
        enabled=model["enabled"], steps=steps, guards=guards, any_order=model["any_order"],
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
             result: Replay | None, duration: float,
             others: list[tuple[list[Observation], str]] | None = None) -> None:
        """``others`` are more traces (observations, color) drawn thin behind the main one."""
        self._last = (gesture, observations, result, duration, others or [])
        self._redraw()

    def _redraw(self) -> None:
        if self._last is None:
            return
        gesture, observations, result, duration, others = self._last
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
                "Test it with the gesture wizard."), justify="center")
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

        for trace, color, line_w in [*((o, col, 1) for o, col in others), (observations, _TRACE, 2)]:
            for li, sig in enumerate(lanes):
                points: list[float] = []
                for o in trace:
                    v = signal_value(sig, o)
                    if v is None:
                        if len(points) >= 4:
                            c.create_line(*points, fill=color, width=line_w)
                        points = []
                        continue
                    points += [x(o.timestamp), y(v, li)]
                if len(points) >= 4:
                    c.create_line(*points, fill=color, width=line_w)

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


class SettingsWindow:
    """Gestures (plot, steps) and general settings, in their own window."""

    def __init__(self, app: MainWindow) -> None:
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title("vn-eye settings")
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.builtin = set(Config().gestures)
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
        ttk.Button(left, text="Set up with wizard…", command=lambda: self.app.open_wizard(self)).pack(fill="x", pady=(12, 0))

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
        self.guards_frame = ttk.Frame(tab)
        self.guards_frame.grid(row=3, column=1, sticky="ew", pady=(8, 0))
        buttons = ttk.Frame(tab)
        buttons.grid(row=4, column=1, sticky="w", pady=(6, 0))
        ttk.Button(buttons, text="+ Add step", command=self._add_step).pack(side="left")
        ttk.Button(buttons, text="+ Add head limit", command=self._add_guard).pack(side="left", padx=(8, 0))
        ttk.Label(buttons, foreground=_MUTED, text="Leave a number empty for no limit.").pack(side="left", padx=10)


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
        self._build_guards()
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
                               "cooldown_s": 1.0, "guards": [], "steps": [{**_new_step("eyes"), "after_max_s": 0.0}]}
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

    def _build_guards(self) -> None:
        frame = self.guards_frame
        for child in frame.winfo_children():
            child.destroy()
        self.guard_vars: dict[tuple[int, str], tk.StringVar] = {}
        guards = self.gestures[self.current]["guards"]
        if not guards:
            return
        ttk.Label(frame, text="Only while the head stays within", foreground=_MUTED).grid(
            row=0, column=0, columnspan=6, sticky="w", padx=3)
        for i, guard in enumerate(guards):
            r = i + 1
            kind = ttk.Combobox(frame, state="readonly", width=8, values=("pitch", "yaw"))
            kind.set(guard["kind"])
            kind.bind("<<ComboboxSelected>>", lambda _e, i=i, w=kind: self._on_guard_kind(i, w.get()))
            kind.grid(row=r, column=0, padx=3, pady=2)
            for key, col in (("above", 1), ("below", 3)):
                ttk.Label(frame, text=key.capitalize()).grid(row=r, column=col, sticky="e")
                var = tk.StringVar(value=_fmt(guard[key]))
                var.trace_add("write", lambda *_a, i=i, k=key: self._on_guard_number(i, k))
                ttk.Entry(frame, textvariable=var, width=7).grid(row=r, column=col + 1, padx=3)
                self.guard_vars[(i, key)] = var
            ttk.Label(frame, text="°").grid(row=r, column=5, sticky="w")
            ttk.Button(frame, text="✕", width=3, command=lambda i=i: self._delete_guard(i)).grid(
                row=r, column=6, padx=3)

    def _on_guard_kind(self, i: int, value: str) -> None:
        self.gestures[self.current]["guards"][i]["kind"] = value
        self._refresh()

    def _on_guard_number(self, i: int, key: str) -> None:
        if self._suppress:
            return
        guard = self.gestures[self.current]["guards"][i]
        self._set_number(guard, key, self.guard_vars[(i, key)].get(), f"Head limit {i + 1} {key}", True)
        self._refresh()

    def _add_guard(self) -> None:
        guards = self.gestures[self.current]["guards"]
        used = {g["kind"] for g in guards}
        kind = next((k for k in ("yaw", "pitch") if k not in used), "yaw")
        guards.append({"kind": kind, "above": -20.0, "below": 20.0})
        self._build_guards()
        self._refresh()

    def _delete_guard(self, i: int) -> None:
        del self.gestures[self.current]["guards"][i]
        self._build_guards()
        self._refresh()

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

    # Live plot

    def _replay(self, config: Config | None, observations: list[Observation]) -> Replay | None:
        if config is None or not observations:
            return None
        try:
            return replay(config, self.current, observations)
        except ValueError:
            return None

    def _refresh(self) -> None:
        """Validates the edits, then re-runs the gesture on the live signal and redraws."""
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

        self._draw_plot(config)

    def _draw_plot(self, config: Config | None) -> None:
        observations = self.app.worker.recent(RECORD_S)
        result = self._replay(config, observations)
        if result is None:
            self.result.configure(text="", foreground=_MUTED)
        elif result.fired_at is not None:
            self.result.configure(text=f"✓ Fires at {result.fired_at:.2f}s", foreground=_OK)
        else:
            self.result.configure(text=f"✕ {result.reason[:1].upper()}{result.reason[1:]}", foreground=_BAD)
        self.plot.draw(self.gestures[self.current], observations, result, RECORD_S)

    def _live_loop(self) -> None:
        if not self.win.winfo_exists():
            return
        try:
            config: Config | None = self.build_config()
        except ValueError:
            config = None
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

    def use_fit(self, name: str, gesture: GestureConfig, takes: list[Take]) -> None:
        """Puts the wizard's result in the editor and applies it."""
        self.gestures[name] = _gesture_model(gesture)
        self._select(name)
        self.apply()

    def close(self) -> None:
        if self.app.wizard is not None and self.app.wizard.settings is self:
            self.app.wizard.close()
        self.app.settings = None
        self.win.destroy()


class WizardWindow:
    """Record takes of one gesture whenever you like, say what each one was
    meant to be, and see the gesture fitted to all of them so far."""

    def __init__(self, app: MainWindow, settings: SettingsWindow | None, name: str) -> None:
        self.app = app
        self.settings = settings
        self.worker = app.worker
        self.base = app.config
        if settings is not None:
            try:
                self.base = settings.build_config()
            except ValueError:
                pass
        self.names = [n for n, g in self.base.gestures.items() if can_tune(g)]
        self.name = name if name in self.names else self.names[0]
        self.takes: list[Take] = []
        self.pending: list[Observation] | None = None
        self.fitted: Fit | None = None
        self._started: float | None = None
        self._timer: str | None = None

        parent = settings.win if settings is not None else app.root
        self.win = tk.Toplevel(parent)
        self.win.title("Gesture wizard")
        self.win.transient(parent)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        # Gestures are off while you record, so your takes send nothing to other windows.
        config = app.config
        quiet = {n: replace(g, enabled=False) for n, g in config.gestures.items()}
        self.worker.set_config(replace(config, gestures=quiet))
        self._build()
        self.win.grab_set()
        self._refit()

    def _build(self) -> None:
        body = ttk.Frame(self.win, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        top = ttk.Frame(body)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(top, text="Gesture").pack(side="left")
        self.gesture = ttk.Combobox(top, state="readonly", width=18, values=self.names)
        self.gesture.set(self.name)
        self.gesture.bind("<<ComboboxSelected>>", lambda _e: self._on_gesture())
        self.gesture.pack(side="left", padx=(6, 0))
        self.hint = ttk.Label(body, foreground=_MUTED, wraplength=900, justify="left")
        self.hint.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        rec = ttk.Frame(body)
        rec.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.record_button = ttk.Button(rec, text="● Record", width=14, command=self._toggle_record)
        self.record_button.pack(side="left")
        self.status = ttk.Label(rec, font="TkHeadingFont")
        self.status.pack(side="left", padx=(12, 0))

        labels = ttk.Frame(body)
        labels.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(labels, text="That take was:").pack(side="left")
        self.label_buttons = []
        for kind, label in KIND_LABELS.items():
            button = ttk.Button(labels, text=label.capitalize(), command=lambda k=kind: self._label(k))
            button.pack(side="left", padx=(6, 0))
            self.label_buttons.append(button)
        button = ttk.Button(labels, text="Discard", command=self._discard)
        button.pack(side="left", padx=(12, 0))
        self.label_buttons.append(button)

        left = ttk.Frame(body)
        left.grid(row=4, column=0, sticky="ns", pady=(12, 0))
        self.take_list = ttk.Treeview(left, columns=("take", "result"), show="headings",
                                      height=10, selectmode="browse")
        self.take_list.heading("take", text="Take")
        self.take_list.heading("result", text="With the fitted settings")
        self.take_list.column("take", width=150)
        self.take_list.column("result", width=260)
        self.take_list.tag_configure("ok", foreground=_OK)
        self.take_list.tag_configure("bad", foreground=_BAD)
        self.take_list.bind("<<TreeviewSelect>>", lambda _e: self._draw())
        self.take_list.pack(fill="y", expand=True)
        ttk.Button(left, text="Delete take", command=self._delete).pack(anchor="w", pady=(4, 0))
        self.plot = PlotEditor(body, lambda _i, _k, _v: None)
        self.plot.canvas.grid(row=4, column=1, sticky="nsew", padx=(10, 0), pady=(12, 0))

        self.notes = ttk.Label(body, wraplength=900, justify="left")
        self.notes.grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))
        bottom = ttk.Frame(body)
        bottom.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.enable = tk.BooleanVar(value=True)
        self.enable_check = ttk.Checkbutton(bottom, variable=self.enable)
        self.use_button = ttk.Button(bottom, text="Use these settings", command=self._use)
        self.use_button.pack(side="right")
        ttk.Button(bottom, text="Cancel", command=self.close).pack(side="right", padx=6)

    def _gesture(self) -> GestureConfig:
        return self.fitted.gesture if self.fitted else self.base.gestures[self.name]

    def _on_gesture(self) -> None:
        name = self.gesture.get()
        if name == self.name:
            return
        if self.takes and not messagebox.askyesno(
                "Gesture wizard", f"Discard your {len(self.takes)} takes of {self.name}?", parent=self.win):
            self.gesture.set(self.name)
            return
        self.name = name
        self.takes = []
        self.pending = None
        self._refit()

    # Recording

    def _toggle_record(self) -> None:
        if self._started is None:
            self.pending = None
            self._started = time.monotonic()
            self.record_button.configure(text="■ Stop")
            self._tick()
            return
        if self._timer is not None:
            self.win.after_cancel(self._timer)
            self._timer = None
        elapsed = time.monotonic() - self._started
        self._started = None
        self.record_button.configure(text="● Record")
        self.pending = self.worker.recent(elapsed)
        self._refresh_controls()
        self._draw()

    def _tick(self) -> None:
        assert self._started is not None
        elapsed = time.monotonic() - self._started
        if elapsed >= MAX_TAKE_S:
            self._toggle_record()
            return
        problem = self._face_problem()
        self.status.configure(text=f"Recording… {elapsed:.1f} s" + (f"   ({problem})" if problem else ""),
                              foreground=_BAD if problem else _OK)
        self._timer = self.win.after(100, self._tick)

    def _face_problem(self) -> str | None:
        if self.worker.engine is None:
            return "the camera isn't running"
        recent = self.worker.recent(0.3)
        signals = {s.signal for s in self.base.gestures[self.name].steps}
        if not recent or any(signal_value(s, recent[-1]) is None for s in signals):
            return "no face"
        return None

    def _label(self, kind: str) -> None:
        if self.pending:
            self.takes.append(Take(kind, self.pending))
            self.pending = None
            self._refit()
            self.take_list.selection_set(str(len(self.takes) - 1))

    def _discard(self) -> None:
        self.pending = None
        self._refresh_controls()
        self._draw()

    def _delete(self) -> None:
        sel = self.take_list.selection()
        if sel:
            del self.takes[int(sel[0])]
            self._refit()

    # Fitting

    def _refit(self) -> None:
        self.fitted = fit(self.base, self.name, self.takes) if self.takes else None
        view = self.take_list
        view.delete(*view.get_children())
        for i, take in enumerate(self.takes):
            assert self.fitted is not None
            result = self.fitted.results[i]
            fired = result.fired_at is not None
            ok = fired == (take.kind == DO)
            text = f"fires at {result.fired_at:.2f}s" if fired else f"doesn't fire: {result.reason}"
            view.insert("", "end", iid=str(i), values=(f"{i + 1}. {KIND_LABELS[take.kind]}",
                        f"{'✓' if ok else '✕'} {text}"), tags=("ok" if ok else "bad",))

        lines = [f"Record takes in any order. Worth recording for {self.name}:"]
        lines += [f"  • {KIND_LABELS[kind]}: {what}" for kind, what in suggestions(self.name)]
        lines.append("Gestures are off while the wizard is open, so nothing is sent to other windows. "
                     "Takes keep only the eye and head numbers, in memory, never images.")
        self.hint.configure(text="\n".join(lines))
        if self.fitted is None:
            self.notes.configure(text="")
        else:
            wrong = sum((r.fired_at is not None) != (t.kind == DO) for t, r in zip(self.takes, self.fitted.results))
            notes = self.fitted.notes or ["Your takes fit the current settings. Nothing changed."]
            summary = ("Every take does what it should." if not wrong else
                       f"{wrong} take(s) don't do what they should: delete a take you got wrong, or "
                       "fine-tune the boxes in the settings window afterward.")
            self.notes.configure(text="\n".join(f"• {n}" for n in notes) + "\n" + summary,
                                 foreground=_OK if not wrong else _BAD)
        if not self.base.gestures[self.name].enabled:
            self.enable_check.configure(text=f"Turn {self.name} on")
            self.enable_check.pack(side="left")
        else:
            self.enable_check.pack_forget()
        self._refresh_controls()
        self._draw()

    def _refresh_controls(self) -> None:
        state = "normal" if self.pending else "disabled"
        for button in self.label_buttons:
            button.configure(state=state)
        has_do = any(t.kind == DO for t in self.takes)
        self.use_button.configure(state="normal" if has_do else "disabled")
        if self.pending is not None:
            length = self.pending[-1].timestamp if self.pending else 0.0
            result = self._result(self.pending)
            then = "" if result is None else (
                f" With the fitted settings it fires at {result.fired_at:.2f}s." if result.fired_at is not None
                else f" With the fitted settings it doesn't fire: {result.reason}.")
            self.status.configure(text=f"Recorded {length:.1f} s. What was it?{then}", foreground=_TRACE)
        elif self._started is None:
            hint = "Do one more take." if has_do else "Select Record, do the gesture once, then select Stop."
            self.status.configure(text=hint, foreground=_MUTED)

    def _result(self, observations: list[Observation]) -> Replay | None:
        if not observations:
            return None
        config = replace(self.base, gestures={**self.base.gestures, self.name: self._gesture()})
        return replay(config, self.name, observations)

    def _draw(self) -> None:
        # Every take is drawn on one plot, each cut to where it moves (plus 1 s
        # either side) and counted from that cut. The picked take is drawn bold.
        sel = self.take_list.selection()
        picked = int(sel[0]) if sel else None
        signals = {s.signal for s in self._gesture().steps if s.signal}
        main: list[Observation] = []
        result: Replay | None = None
        others: list[tuple[list[Observation], str]] = []
        shown = [(None, self.pending)] if self.pending is not None else list(enumerate(t.observations for t in self.takes))
        for i, observations in shown:
            start, cut = trim(observations, signals)
            if self.pending is not None or i == picked:
                main = cut
                found = self._result(observations)
                if found is not None:
                    result = Replay(None if found.fired_at is None else found.fired_at - start, found.reason,
                                    tuple((s, t - start) for s, t in found.steps))
            else:
                ok = self.fitted is not None and (self.fitted.results[i].fired_at is not None) == (self.takes[i].kind == DO)
                others.append((cut, _tint(_OK if ok else _BAD, 0.45)))
        if self.pending is not None:
            others = [(trim(t.observations, signals)[1], _GRID_TRACE) for t in self.takes]
        length = max((c[-1].timestamp for c in [main, *(o for o, _ in others)] if c), default=0.0)
        duration = max(1.0, math.ceil(length)) if length else RECORD_S
        self.plot.draw(_gesture_model(self._gesture()), main, result, duration, others)

    def _use(self) -> None:
        assert self.fitted is not None
        gesture = replace(self.fitted.gesture, enabled=self.fitted.gesture.enabled or self.enable.get())
        app, settings, name, takes = self.app, self.settings, self.name, self.takes
        self.close()
        if settings is not None:
            settings.use_fit(name, gesture, takes)
        else:
            app.use_fit(name, gesture, takes)

    def close(self) -> None:
        if self._timer is not None:
            self.win.after_cancel(self._timer)
        self.worker.set_config(self.app.config)
        self.app.wizard = None
        self.win.grab_release()
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
