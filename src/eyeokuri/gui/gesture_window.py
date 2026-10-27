"""The gesture window: one gesture's output, plot editor, steps table and head limits."""

from __future__ import annotations

import sys
import tkinter as tk
from dataclasses import replace
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Any

from eyeokuri import theme
from eyeokuri.config import GUARD_SIGNALS, SIGNALS, Config, GestureConfig
from eyeokuri.eyes import Observation
from eyeokuri.gui.model import (
    RECORD_S, SIGNAL_PLOTS, fmt, gesture_config, gesture_model, new_step, show_choice, step_choices, users_of,
)
from eyeokuri.gui.live_edit import LiveEdit
from eyeokuri.gui.plot import PlotEditor
from eyeokuri.gui.tkutil import id_box, place_over
from eyeokuri.i18n import _
from eyeokuri.keys import from_tk_event
from eyeokuri.labels import show_gesture, show_signal
from eyeokuri.outputs import APP_OUTPUTS, OUTPUT_NAMES
from eyeokuri.triggers import Replay, replay
from eyeokuri.tuning import Take, can_tune

if TYPE_CHECKING:
    from eyeokuri.gui.main_window import MainWindow


_LIVE_REFRESH_MS = 250


class GestureWindow:
    """Edits one gesture. Edits apply live; OK saves, Cancel goes back.

    A new gesture (``gesture`` given) isn't in the settings until you press OK."""

    def __init__(self, app: MainWindow, name: str, gesture: GestureConfig | None = None) -> None:
        self.app = app
        self.name = name
        self.new = gesture is not None
        self.builtin = name in Config().gestures
        self.model = gesture_model(gesture or app.config.gestures[name])
        self._suppress = False

        self.win = tk.Toplevel(app.root)
        self.win.withdraw()
        self.title = f"{show_gesture(name)} – eyeokuri"
        self.win.title(self.title)
        self.win.protocol("WM_DELETE_WINDOW", self._close_box)
        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(0, weight=1)
        body = ttk.Frame(self.win, padding=8)
        body.grid(row=0, column=0, sticky="nsew")
        self._build(body)

        bottom = ttk.Frame(self.win, padding=(8, 0, 8, 8))
        bottom.grid(row=1, column=0, sticky="ew")
        self.message = ttk.Label(bottom, text="", foreground=theme.BAD, wraplength=640)
        self.message.pack(side="top", anchor="w", pady=(0, 6))
        self.delete_button = ttk.Button(bottom, text=_("Delete"), command=self._delete,
                                        state="disabled" if self.builtin else "normal")
        self.delete_button.pack(side="left")
        ttk.Button(bottom, text=_("Reset to default"), command=self._reset,
                   state="normal" if self.builtin else "disabled").pack(side="left", padx=(6, 0))
        ttk.Button(bottom, text=_("Cancel"), command=self.cancel).pack(side="right")
        self.ok_button = ttk.Button(bottom, text=_("OK"), style="Accent.TButton", command=self.ok)
        self.ok_button.pack(side="right", padx=6)
        self.edit = LiveEdit(app, self.win, self.message, self.ok_button, self._edited)

        self._load_fields()
        place_over(self.win, app.root)
        self._live_loop()

    # Model

    def build_config(self) -> Config:
        """The settings in use with this gesture's edits; raises ValueError if they aren't valid."""
        return self.edit.config()

    def _edited(self) -> Config:
        """The settings in use with this gesture's edits. A new gesture goes after the others."""
        base = self.app.config
        return replace(base, gestures={**base.gestures, self.name: gesture_config(self.model)})

    # Fields

    def _build(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)

        # The wizard is the usual way to set the limits, so it leads the window.
        banner = ttk.Frame(tab, padding=8, relief="groove")
        banner.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        banner.columnconfigure(1, weight=1)
        self.wizard_button = ttk.Button(banner, text=_("Set up with wizard…"), style="Accent.TButton",
                                        command=lambda: self.app.open_wizard(self))
        self.wizard_button.grid(row=0, column=0, rowspan=2, padx=(0, 12))
        ttk.Label(banner, text=_("Recommended: let the wizard set the limits"), font="TkHeadingFont").grid(
            row=0, column=1, sticky="w")
        ttk.Label(banner, foreground=theme.MUTED, text=_(
            "Do the gesture a few times and the wizard fits the limits and time windows to you. "
            "You can also edit them by hand below.")).grid(row=1, column=1, sticky="w")

        top = ttk.Frame(tab)
        top.grid(row=1, column=0, sticky="ew")
        ttk.Label(top, text=_("Output")).pack(side="left", padx=(0, 4))
        # Editable: any key or combination (f5, ctrl+s) can be typed, or captured below.
        self.output_var = tk.StringVar()
        self.output_var.trace_add("write", lambda *_a: self._on_gesture_field())
        self.output = ttk.Combobox(top, width=18, textvariable=self.output_var,
                                   values=["(none)", *OUTPUT_NAMES, *sorted(APP_OUTPUTS)])
        self.output.pack(side="left")
        self.capture_button = ttk.Button(top, text=_("Press a key…"), command=self._toggle_capture)
        self.capture_button.pack(side="left", padx=(4, 0))
        self._capturing = False
        self.any_order = tk.BooleanVar()
        ttk.Checkbutton(top, text=_("Steps in any order"), variable=self.any_order,
                        command=self._on_gesture_field).pack(side="left", padx=(14, 0))
        self.gesture_vars: dict[str, tk.StringVar] = {}
        for key, label in (("within_s", _("Within")), ("cooldown_s", _("Cooldown"))):
            ttk.Label(top, text=label).pack(side="left", padx=(14, 4))
            var = tk.StringVar()
            var.trace_add("write", lambda *_a, k=key: self._on_gesture_number(k))
            ttk.Entry(top, textvariable=var, width=6).pack(side="left")
            ttk.Label(top, text="s").pack(side="left", padx=(2, 0))
            self.gesture_vars[key] = var

        middle = ttk.Frame(tab)
        middle.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        middle.columnconfigure(0, weight=1)
        middle.rowconfigure(1, weight=1)
        self.result = ttk.Label(middle, text="", font="TkHeadingFont")
        self.result.grid(row=0, column=0, sticky="w")
        self.plot = PlotEditor(middle, self._on_drag)
        self.plot.canvas.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        ttk.Label(middle, foreground=theme.MUTED, text=_(
            "Drag a box edge to change a threshold or a time limit. Boxes after step 1 start when "
            "the previous step was reached in this recording.")).grid(row=2, column=0, sticky="w", pady=(4, 0))

        self.steps_frame = ttk.Frame(tab)
        self.steps_frame.grid(row=3, column=0, sticky="ew", pady=(8, 0))

    def _load_fields(self) -> None:
        """Shows the model in the widgets, after opening, a reset or the wizard."""
        m = self.model
        self._suppress = True
        self._stop_capture()
        self.output_var.set(m["output"] or "(none)")
        self.any_order.set(m["any_order"])
        for key, var in self.gesture_vars.items():
            var.set(fmt(m[key]))
        self._suppress = False
        self.edit.errors.clear()
        self._build_steps()
        self._build_guards()
        self._refresh()

    def _on_gesture_field(self) -> None:
        if self._suppress:
            return
        m = self.model
        output = self.output_var.get().strip().lower()
        # Invalid text is stored too; build_config() reports it, and nothing applies until it's fixed.
        m["output"] = "" if output in ("", "(none)") else output
        if m["any_order"] != self.any_order.get():
            m["any_order"] = self.any_order.get()
            self._build_steps()
        self._refresh()

    def _toggle_capture(self) -> None:
        if self._capturing:
            self._stop_capture()
            return
        self._capturing = True
        self.capture_button.configure(text=_("Press a key now (click to cancel)"))
        # Keys go to the focused button; "break" stops Space or Tab from acting on it.
        self.capture_button.focus_set()
        self.capture_button.bind("<KeyPress>", self._on_capture_key)
        self.capture_button.bind("<FocusOut>", lambda _e: self._stop_capture())

    def _on_capture_key(self, event: tk.Event) -> str:
        name = from_tk_event(event.keysym, event.state, sys.platform)
        if name is not None:
            self._stop_capture()
            self.output_var.set(name)
        return "break"

    def _stop_capture(self) -> None:
        if not self._capturing:
            return
        self._capturing = False
        self.capture_button.unbind("<KeyPress>")
        self.capture_button.unbind("<FocusOut>")
        self.capture_button.configure(text=_("Press a key…"))

    def _on_gesture_number(self, key: str) -> None:
        if self._suppress:
            return
        self._set_number(self.model, key, self.gesture_vars[key].get(), key, optional=False)
        self._refresh()

    def _set_number(self, target: dict[str, Any], key: str, text: str, label: str, optional: bool) -> None:
        text = text.strip()
        try:
            value = None if text == "" and optional else float(text or 0)
        except ValueError:
            self.edit.errors[label] = _("Not a number:") + f" {label} = {text!r}"
            return
        self.edit.errors.pop(label, None)
        target[key] = value

    # Steps table

    def _build_steps(self) -> None:
        frame = self.steps_frame
        for child in frame.winfo_children():
            child.destroy()
        self.step_vars: dict[tuple[int, str], tk.StringVar] = {}
        headers = ("", _("Signal"), _("Above"), "", _("Below"), "", _("After previous: min"), _("max"), _("Hold"), "")
        for col, text in enumerate(headers):
            ttk.Label(frame, text=text, foreground=theme.MUTED).grid(row=0, column=col, sticky="w", padx=3)
        m = self.model
        choices = step_choices(self.app.config.gestures, self.name)
        for i, step in enumerate(m["steps"]):
            r = i + 1
            color = theme.STEP_COLORS[i % len(theme.STEP_COLORS)]
            tk.Label(frame, text=str(i + 1), background=color, foreground="white", width=2).grid(
                row=r, column=0, padx=3, pady=2)
            id_box(frame, choices, show_choice, (step["kind"], step["gesture"]),
                   lambda c, i=i: self._on_kind(i, c)).grid(
                row=r, column=1, sticky="ew", padx=3)
            is_signal = step["kind"] in SIGNALS
            unit = SIGNALS[step["kind"]].symbol if is_signal else ""
            first = i == 0 and not m["any_order"]
            cells = (("above", 2, True, is_signal), ("below", 4, True, is_signal),
                     ("after_min_s", 6, False, not first), ("after_max_s", 7, False, not first),
                     ("hold_s", 8, False, is_signal))
            for key, col, optional, enabled in cells:
                var = tk.StringVar(value=fmt(step[key]))
                var.trace_add("write", lambda *_a, i=i, k=key, opt=optional: self._on_step_number(i, k, opt))
                entry = ttk.Entry(frame, textvariable=var, width=7, state="normal" if enabled else "disabled")
                entry.grid(row=r, column=col, padx=3)
                self.step_vars[(i, key)] = var
            ttk.Label(frame, text=unit).grid(row=r, column=3, sticky="w")
            ttk.Label(frame, text=unit).grid(row=r, column=5, sticky="w")
            ttk.Button(frame, text="✕", width=3, command=lambda i=i: self._delete_step(i),
                       state="normal" if len(m["steps"]) > 1 else "disabled").grid(row=r, column=9, padx=3)
        ttk.Button(frame, text=_("+ Add step"), command=self._add_step).grid(
            row=len(m["steps"]) + 1, column=1, sticky="w", padx=3, pady=(4, 0))
        ttk.Label(frame, foreground=theme.MUTED, text=_("Leave a number empty for no limit.")).grid(
            row=len(m["steps"]) + 1, column=2, columnspan=8, sticky="w", padx=10, pady=(4, 0))
        self._add_guard_rows(frame, len(m["steps"]) + 2)

    def _build_guards(self) -> None:
        """Head limits share the steps table's columns, so rebuilding one rebuilds both."""
        self._build_steps()

    def _add_guard_rows(self, frame: ttk.Frame, row: int) -> None:
        self.guard_vars: dict[tuple[int, str], tk.StringVar] = {}
        guards = self.model["guards"]
        ttk.Label(frame, text=_("Only while the head stays within"), foreground=theme.MUTED).grid(
            row=row, column=0, columnspan=10, sticky="w", padx=3, pady=(10, 0))
        for i, guard in enumerate(guards):
            r = row + 1 + i
            tk.Label(frame, text="•", width=2).grid(row=r, column=0, padx=3, pady=2)
            id_box(frame, GUARD_SIGNALS, show_signal, guard["kind"], lambda k, i=i: self._on_guard_kind(i, k)).grid(
                row=r, column=1, sticky="ew", padx=3)
            for key, col in (("above", 2), ("below", 4)):
                var = tk.StringVar(value=fmt(guard[key]))
                var.trace_add("write", lambda *_a, i=i, k=key: self._on_guard_number(i, k))
                ttk.Entry(frame, textvariable=var, width=7).grid(row=r, column=col, padx=3)
                ttk.Label(frame, text="°").grid(row=r, column=col + 1, sticky="w")
                self.guard_vars[(i, key)] = var
            ttk.Button(frame, text="✕", width=3, command=lambda i=i: self._delete_guard(i)).grid(
                row=r, column=9, padx=3)
        # Lined up with "+ Add step" above, in the Signal column.
        ttk.Button(frame, text=_("+ Add head limit"), command=self._add_guard).grid(
            row=row + 1 + len(guards), column=1, sticky="w", padx=3, pady=(4, 0))
        ttk.Label(frame, foreground=theme.MUTED, text=_("Leave a number empty for no limit.")).grid(
            row=row + 1 + len(guards), column=2, columnspan=8, sticky="w", padx=10, pady=(4, 0))

    def _on_guard_kind(self, i: int, value: str) -> None:
        self.model["guards"][i]["kind"] = value
        self._refresh()

    def _on_guard_number(self, i: int, key: str) -> None:
        if self._suppress:
            return
        guard = self.model["guards"][i]
        self._set_number(guard, key, self.guard_vars[(i, key)].get(), _("Head limit") + f" {i + 1} · {key}", True)
        self._refresh()

    def _add_guard(self) -> None:
        guards = self.model["guards"]
        used = {g["kind"] for g in guards}
        # yaw before pitch: turning the head away is the usual reason for a limit.
        kind = next((k for k in reversed(GUARD_SIGNALS) if k not in used), GUARD_SIGNALS[-1])
        guards.append({"kind": kind, "above": -20.0, "below": 20.0})
        self._build_guards()
        self._refresh()

    def _delete_guard(self, i: int) -> None:
        del self.model["guards"][i]
        self._build_guards()
        self._refresh()

    def _on_kind(self, i: int, choice: tuple[str, str]) -> None:
        steps = self.model["steps"]
        old = steps[i]
        kind, gesture = choice
        new = {**new_step(kind), "gesture": gesture}
        new["after_min_s"], new["after_max_s"] = old["after_min_s"], old["after_max_s"]
        steps[i] = new
        self._build_steps()
        self._refresh()

    def _on_step_number(self, i: int, key: str, optional: bool) -> None:
        if self._suppress:
            return
        step = self.model["steps"][i]
        self._set_number(step, key, self.step_vars[(i, key)].get(), _("Step") + f" {i + 1} · {key}", optional)
        self._refresh()

    def _add_step(self) -> None:
        steps = self.model["steps"]
        kind = steps[-1]["kind"] if steps else "eyes"
        steps.append(new_step(kind if kind in SIGNALS else "eyes"))
        self._build_steps()
        self._refresh()

    def _delete_step(self, i: int) -> None:
        steps = self.model["steps"]
        if len(steps) > 1:
            del steps[i]
            self.edit.errors.clear()
            self._build_steps()
            self._refresh()

    def _on_drag(self, i: int, key: str, value: float) -> None:
        step = self.model["steps"][i]
        gap = SIGNAL_PLOTS[step["kind"]].snap * 2
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
        self.step_vars[(i, key)].set(fmt(value))
        self._suppress = False
        self._refresh()

    # Live plot

    def _replay(self, config: Config | None, observations: list[Observation]) -> Replay | None:
        if config is None or not observations:
            return None
        try:
            return replay(config, self.name, observations)
        except ValueError:
            return None

    def _refresh(self) -> None:
        """Validates the edits, re-runs the gesture on the live signal and redraws,
        then applies the edits once they stop changing."""
        config = self.edit.refresh()
        # The wizard fits boxes, so it needs valid settings where every step has one.
        tunable = config is not None and can_tune(config.gestures[self.name])
        self.wizard_button.configure(state="normal" if tunable else "disabled")
        self._draw_plot(config)

    def _draw_plot(self, config: Config | None) -> None:
        observations = self.app.worker.recent(RECORD_S)
        result = self._replay(config, observations)
        if result is None:
            self.result.configure(text="", foreground=theme.MUTED)
        elif result.fired_at is not None:
            self.result.configure(text="✓ " + _("Fires:") + f" {result.fired_at:.2f}s", foreground=theme.OK)
        else:
            self.result.configure(text=f"✕ {result.reason[:1].upper()}{result.reason[1:]}", foreground=theme.BAD)
        self.plot.draw(self.model, observations, result, RECORD_S)

    def _live_loop(self) -> None:
        if not self.win.winfo_exists():
            return
        try:
            config: Config | None = self.build_config()
        except ValueError:
            config = None
        self._draw_plot(config)
        self.win.after(_LIVE_REFRESH_MS, self._live_loop)

    # Buttons

    def _delete(self) -> None:
        if self.builtin:
            return
        users = users_of(self.edit.opened_with.gestures, self.name)
        if users:
            messagebox.showerror(_("Delete gesture"), _("Other gestures use this one as a step. Remove it from them first:")
                                 + f"\n\n{', '.join(map(show_gesture, users))}", parent=self.win)
            return
        if not messagebox.askyesno(_("Delete gesture"), _("Delete this gesture?") + f"\n\n{show_gesture(self.name)}", parent=self.win):
            return
        if self.new:
            self.cancel()
            return
        opened_with = self.edit.opened_with
        gestures = {n: g for n, g in opened_with.gestures.items() if n != self.name}
        try:
            self.app.save_config(replace(opened_with, gestures=gestures))
        except OSError as e:
            self.edit.show_error(str(e))
            return
        self.app.worker.log(f"{self.name}: deleted")
        self._close()

    def _reset(self) -> None:
        """Goes back to the built-in settings. On or off stays as it is: the main window's toggle owns that."""
        if self.builtin:
            enabled = self.model["enabled"]
            self.model = gesture_model(replace(Config().gestures[self.name], enabled=enabled))
            self._load_fields()

    def ok(self) -> None:
        """Saves and closes; if saving fails, the window stays open with your edits."""
        if self.edit.save() is not None:
            self._close()

    def cancel(self) -> None:
        """Goes back to the settings in use when the window opened, and closes."""
        self.edit.revert()
        self._close()

    def _close_box(self) -> None:
        """The window's close button cancels, but asks first so one click can't undo your tuning."""
        # A new gesture is lost when it closes, even unchanged.
        if self.edit.may_discard(self.title, changed=self.new):
            self.cancel()

    def use_fit(self, gesture: GestureConfig, takes: list[Take]) -> None:
        """Puts the wizard's result in the editor and applies it; OK saves it."""
        self.model = gesture_model(gesture)
        self._load_fields()
        self.edit.apply()

    def _close(self) -> None:
        self.edit.close()
        if self.app.wizard is not None and self.app.wizard.owner is self:
            self.app.wizard.close()
        self.app.gesture_window = None
        self.app.push_config()
        self.win.destroy()
