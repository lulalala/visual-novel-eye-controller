"""The plot of recorded signals with one draggable box per step."""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable

from eyeokuri import theme
from eyeokuri.config import SIGNALS
from eyeokuri.eyes import Observation
from eyeokuri.gui.model import LANE_HINTS, PLOT_RANGES, RECORD_S
from eyeokuri.triggers import Replay, signal_value


def tint(color: str, amount: float) -> str:
    """The color mixed with white, for box fills that the trace stays readable on."""
    r, g, b = (int(color[k:k + 2], 16) for k in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(round(v + (255 - v) * amount) for v in (r, g, b))


class PlotEditor:
    """A plot of the recorded signals with one draggable box per step."""

    L, R, TOP, LANE_H, GAP, AXIS = 58, 14, 24, 150, 34, 26

    def __init__(self, parent: tk.Misc, on_drag: Callable[[int, str, float], None]) -> None:
        self.canvas = tk.Canvas(parent, width=680, height=220, background=theme.SURFACE,
                                highlightthickness=1, highlightbackground=theme.LINE)
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
            c.create_text(width / 2, height / 2, fill=theme.MUTED, text=(
                "This gesture's steps are other gestures, so there is nothing to plot.\n"
                "Test it with the gesture wizard."), justify="center")
            return
        self._geo = (width, duration, lanes)

        def x(t: float) -> float:
            return self.L + max(0.0, min(duration, t)) / duration * (width - self.L - self.R)

        def lane_top(li: int) -> float:
            return self.TOP + li * (self.LANE_H + self.GAP)

        def y(v: float, li: int) -> float:
            lo, hi = PLOT_RANGES[lanes[li]][:2]
            v = max(lo, min(hi, v))
            return lane_top(li) + (1 - (v - lo) / (hi - lo)) * self.LANE_H

        bottom = height - self.AXIS
        tick = 0.5
        t = 0.0
        while t <= duration + 1e-9:
            c.create_line(x(t), self.TOP, x(t), bottom, fill=theme.GRID)
            c.create_text(x(t), bottom + 13, text=f"{t:g} s", fill=theme.MUTED, font="TkSmallCaptionFont")
            t += tick
        for li, sig in enumerate(lanes):
            lo, hi, grid, unit, _ = PLOT_RANGES[sig]
            c.create_text(self.L, lane_top(li) - 10, anchor="w", text=LANE_HINTS[sig], fill=theme.MUTED,
                          font="TkSmallCaptionFont")
            for v in grid:
                zero = (v == 0 and sig != "eyes") or (v == 1.0 and sig == "eyes")
                c.create_line(self.L, y(v, li), width - self.R, y(v, li), fill=theme.ZERO if zero else theme.GRID)
                label = f"{v:.2f}" if sig == "eyes" else f"{v:g}{unit}"
                c.create_text(self.L - 6, y(v, li), anchor="e", text=label, fill=theme.MUTED, font="TkSmallCaptionFont")

        # Each step's box. A box after the first starts at the moment the
        # previous step was reached, so its edges are the allowed time after it.
        reached = dict(result.steps) if result else {}
        order = [i for i, _ in sorted(reached.items(), key=lambda kv: kv[1])]
        steps = gesture["steps"]
        for i, step in enumerate(steps):
            if step["kind"] not in SIGNALS:
                continue
            li = lanes.index(step["kind"])
            color = theme.STEP_COLORS[i % len(theme.STEP_COLORS)]
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
                               dash="" if anchored else (4, 3), fill=tint(color, 0.86 if anchored else 0.94))
            c.create_rectangle(bx + 3, y_top + 3, bx + 19, y_top + 19, fill=color, outline="")
            c.create_text(bx + 11, y_top + 11, text=str(i + 1), fill="white", font="TkSmallCaptionFont")
            unit = PLOT_RANGES[step["kind"]][3]
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

        for trace, color, line_w in [*((o, col, 1) for o, col in others), (observations, theme.TRACE, 2)]:
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
                              fill=theme.STEP_COLORS[i % len(theme.STEP_COLORS)], outline="white", width=2)
        if result is not None and result.fired_at is not None:
            fx = x(result.fired_at)
            c.create_line(fx, self.TOP, fx, bottom, fill=theme.OK, dash=(4, 3), width=2)
            left = fx > width - 90
            c.create_text(fx - 4 if left else fx + 4, bottom - 4, anchor="se" if left else "sw", fill=theme.OK,
                          text=f"fires {result.fired_at:.2f}s", font="TkSmallCaptionFont")
        if not observations:
            c.create_text(width / 2, self.TOP + 40, fill=theme.MUTED, text="No signal yet. Is the camera running?")

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
            lo, hi, _, _, snap = PLOT_RANGES[signal]
            top = self.TOP + li * (self.LANE_H + self.GAP)
            v = lo + (1 - (event.y - top) / self.LANE_H) * (hi - lo)
            v = round(max(lo, min(hi, v)) / snap) * snap
            self._on_drag(step, kind, round(v, 2))
        elif prev is not None:
            t = (event.x - self.L) / (width - self.L - self.R) * duration
            self._on_drag(step, kind, max(0.0, round(t - prev, 2)))

    def _release(self) -> None:
        self._drag = None
