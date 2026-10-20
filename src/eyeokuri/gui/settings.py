"""The settings window: gesture list, plot editor, steps table and general settings."""

from __future__ import annotations

import sys
import tkinter as tk
from dataclasses import fields, replace
from tkinter import messagebox, simpledialog, ttk
from typing import TYPE_CHECKING, Any

from eyeokuri import theme
from eyeokuri.config import SIGNALS, Config, GestureConfig, StepConfig
from eyeokuri.engine import check_config
from eyeokuri.eyes import Observation
from eyeokuri.gui.camera import CameraPicker
from eyeokuri.gui.model import (
    GESTURE_NAME, PLOT_RANGES, RECORD_S, fmt, gesture_config, gesture_model, new_step,
)
from eyeokuri.gui.plot import PlotEditor
from eyeokuri.gui.tkutil import place_over
from eyeokuri.keys import from_tk_event
from eyeokuri.outputs import APP_OUTPUTS, OUTPUT_NAMES
from eyeokuri.triggers import Replay, replay
from eyeokuri.tuning import Take

if TYPE_CHECKING:
    from eyeokuri.gui.main_window import MainWindow


_LIVE_REFRESH_MS = 250
# Edits apply once they stop for this long, so typing "12" doesn't open camera 1 first.
_APPLY_DELAY_MS = 400
# Settings that stay in the config file but not on the General tab. They only
# decide which frames the eye baseline learns from, not when a gesture fires.
_HIDDEN_GENERAL = {("eyes", "close_ratio"), ("eyes", "open_ratio")}
# Settings sections on the General tab, and on the Advanced tab for the baseline settings.
_GENERAL_SECTIONS = ("camera", "feedback")
_ADVANCED_SECTIONS = ("eyes", "head")
# One-line help beside each General field, in user terms.
_GENERAL_HELP = {
    ("camera", "index"): "Which camera to use. 0 is usually the built-in one.",
    ("camera", "width"): "Frame width in pixels (at least 160).",
    ("camera", "height"): "Frame height in pixels (at least 120).",
    ("camera", "fps"): "Frames per second to ask the camera for.",
    ("eyes", "baseline_window_s"): "Seconds of history used to learn your usual open-eye level. "
                                   "Try 5 if lighting or distance changes quickly.",
    ("eyes", "warmup_s"): "Seconds to learn before blinks can trigger. Must be below the window.",
    ("eyes", "require_both_eyes"): "Both eyes must close, so a wink doesn't count.",
    ("head", "baseline_window_s"): "Seconds of history used to learn your usual head position. "
                                   "Raise it if looking away for a while shifts your zero.",
    ("head", "warmup_s"): "Seconds to learn before head gestures can trigger. Must be below the window.",
    ("feedback", "sound"): "Play a sound when a gesture fires or you pause.",
    ("feedback", "log_rejected"): "Log gestures that were detected but didn't fire, and why.",
}


class SettingsWindow:
    """Gestures (plot, steps) and general settings, in their own window."""

    def __init__(self, app: MainWindow) -> None:
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.withdraw()
        self.win.title("eyeokuri settings")
        self.win.protocol("WM_DELETE_WINDOW", self._close_box)
        self.builtin = set(Config().gestures)
        self._suppress = False
        self._field_errors: dict[str, str] = {}
        self.camera_picker: CameraPicker | None = None
        # Cancel goes back to these.
        self._opened_with = app.config
        self._apply_id: str | None = None
        self._load(app.config)

        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(0, weight=1)
        notebook = ttk.Notebook(self.win)
        notebook.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        gestures_tab = ttk.Frame(notebook, padding=8)
        general_tab = ttk.Frame(notebook, padding=12)
        notebook.add(gestures_tab, text="Gestures")
        advanced_tab = ttk.Frame(notebook, padding=12)
        notebook.add(general_tab, text="General")
        notebook.add(advanced_tab, text="Advanced")
        self._build_gestures_tab(gestures_tab)
        self._build_general_tabs(general_tab, advanced_tab)

        bottom = ttk.Frame(self.win, padding=(8, 0, 8, 8))
        bottom.grid(row=1, column=0, sticky="ew")
        self.message = ttk.Label(bottom, text="", foreground=theme.BAD, wraplength=640)
        self.message.pack(side="left", fill="x", expand=True)
        ttk.Button(bottom, text="Cancel", command=self.cancel).pack(side="right")
        self.ok_button = ttk.Button(bottom, text="OK", style="Accent.TButton", command=self.ok)
        self.ok_button.pack(side="right", padx=6)

        self._select(next(iter(self.gestures)))
        place_over(self.win, app.root)
        self._live_loop()

    # Model

    def _load(self, config: Config) -> None:
        self.gestures = {name: gesture_model(g) for name, g in config.gestures.items()}
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
        gestures = {name: gesture_config(m) for name, m in self.gestures.items()}
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
        # Editable: any key or combination (f5, ctrl+s) can be typed, or captured below.
        self.output_var = tk.StringVar()
        self.output_var.trace_add("write", lambda *_a: self._on_gesture_field())
        self.output = ttk.Combobox(top, width=18, textvariable=self.output_var,
                                   values=["(none)", *OUTPUT_NAMES, *sorted(APP_OUTPUTS)])
        self.output.pack(side="left")
        self.capture_button = ttk.Button(top, text="Press a key…", command=self._toggle_capture)
        self.capture_button.pack(side="left", padx=(4, 0))
        self._capturing = False
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
        ttk.Label(middle, foreground=theme.MUTED, text=(
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
        ttk.Label(buttons, foreground=theme.MUTED, text="Leave a number empty for no limit.").pack(side="left", padx=10)


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
        self._stop_capture()
        self.output_var.set(m["output"] or "(none)")
        self.any_order.set(m["any_order"])
        for key, var in self.gesture_vars.items():
            var.set(fmt(m[key]))
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
        output = self.output_var.get().strip().lower()
        # Invalid text is stored too; build_config() reports it, and nothing applies until it's fixed.
        m["output"] = "" if output in ("", "(none)") else output
        if m["any_order"] != self.any_order.get():
            m["any_order"] = self.any_order.get()
            self._build_steps()
        self._refresh_list()
        self._refresh()

    def _toggle_capture(self) -> None:
        if self._capturing:
            self._stop_capture()
            return
        self._capturing = True
        self.capture_button.configure(text="Press a key now (click to cancel)")
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
        self.capture_button.configure(text="Press a key…")

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
        if not GESTURE_NAME.fullmatch(name) or name in self.gestures:
            messagebox.showerror("New gesture", f"{name!r} is taken or has other characters than "
                                 "letters, digits, _ and -.", parent=self.win)
            return
        first = StepConfig(signal="eyes", below_ratio=0.55)
        self.gestures[name] = gesture_model(GestureConfig(steps=[first]))
        self._select(name)

    def _delete_gesture(self) -> None:
        if self.current in self.builtin:
            return
        if messagebox.askyesno("Delete gesture", f"Delete {self.current}?", parent=self.win):
            del self.gestures[self.current]
            self._select(next(iter(self.gestures)))

    def _reset_gesture(self) -> None:
        if self.current in self.builtin:
            self.gestures[self.current] = gesture_model(Config().gestures[self.current])
            self._select(self.current)

    # Steps table

    def _build_steps(self) -> None:
        frame = self.steps_frame
        for child in frame.winfo_children():
            child.destroy()
        self.step_vars: dict[tuple[int, str], tk.StringVar] = {}
        headers = ("", "Signal", "Above", "", "Below", "", "After previous: min", "max", "Hold", "")
        for col, text in enumerate(headers):
            ttk.Label(frame, text=text, foreground=theme.MUTED).grid(row=0, column=col, sticky="w", padx=3)
        m = self.gestures[self.current]
        kinds = [*SIGNALS, *(f"gesture: {n}" for n in self.gestures if n != self.current)]
        for i, step in enumerate(m["steps"]):
            r = i + 1
            color = theme.STEP_COLORS[i % len(theme.STEP_COLORS)]
            tk.Label(frame, text=str(i + 1), background=color, foreground="white", width=2).grid(
                row=r, column=0, padx=3, pady=2)
            kind = ttk.Combobox(frame, state="readonly", width=18, values=kinds)
            kind.set(f"gesture: {step['gesture']}" if step["kind"] == "gesture" else step["kind"])
            kind.bind("<<ComboboxSelected>>", lambda _e, i=i, w=kind: self._on_kind(i, w.get()))
            kind.grid(row=r, column=1, padx=3)
            is_signal = step["kind"] in SIGNALS
            unit = PLOT_RANGES[step["kind"]][3] if is_signal else ""
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

    def _build_guards(self) -> None:
        frame = self.guards_frame
        for child in frame.winfo_children():
            child.destroy()
        self.guard_vars: dict[tuple[int, str], tk.StringVar] = {}
        guards = self.gestures[self.current]["guards"]
        if not guards:
            return
        ttk.Label(frame, text="Only while the head stays within", foreground=theme.MUTED).grid(
            row=0, column=0, columnspan=6, sticky="w", padx=3)
        for i, guard in enumerate(guards):
            r = i + 1
            kind = ttk.Combobox(frame, state="readonly", width=8, values=("pitch", "yaw"))
            kind.set(guard["kind"])
            kind.bind("<<ComboboxSelected>>", lambda _e, i=i, w=kind: self._on_guard_kind(i, w.get()))
            kind.grid(row=r, column=0, padx=3, pady=2)
            for key, col in (("above", 1), ("below", 3)):
                ttk.Label(frame, text=key.capitalize()).grid(row=r, column=col, sticky="e")
                var = tk.StringVar(value=fmt(guard[key]))
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
            new = {**new_step("gesture"), "gesture": value.removeprefix("gesture: ")}
        else:
            new = new_step(value)
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
        steps.append(new_step(kind if kind in SIGNALS else "eyes"))
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
        gap = PLOT_RANGES[step["kind"]][4] * 2
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
            return replay(config, self.current, observations)
        except ValueError:
            return None

    def _refresh(self) -> None:
        """Validates the edits, re-runs the gesture on the live signal and redraws,
        then applies the edits once they stop changing."""
        if self._apply_id is not None:
            self.win.after_cancel(self._apply_id)
            self._apply_id = None
        try:
            config: Config | None = self.build_config()
            self.message.configure(text="")
            self.ok_button.configure(state="normal")
            self._apply_id = self.win.after(_APPLY_DELAY_MS, self._apply)
        except ValueError as e:
            config = None
            self.message.configure(text=str(e), foreground=theme.BAD)
            self.ok_button.configure(state="disabled")

        self._draw_plot(config)

    def _draw_plot(self, config: Config | None) -> None:
        observations = self.app.worker.recent(RECORD_S)
        result = self._replay(config, observations)
        if result is None:
            self.result.configure(text="", foreground=theme.MUTED)
        elif result.fired_at is not None:
            self.result.configure(text=f"✓ Fires at {result.fired_at:.2f}s", foreground=theme.OK)
        else:
            self.result.configure(text=f"✕ {result.reason[:1].upper()}{result.reason[1:]}", foreground=theme.BAD)
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

    # General and Advanced tabs

    def _build_general_tabs(self, general: ttk.Frame, advanced: ttk.Frame) -> None:
        self.general_vars: list[Any] = []
        self._build_settings_tab(general, _GENERAL_SECTIONS, "Changing camera settings reopens the camera.")
        self._build_settings_tab(advanced, _ADVANCED_SECTIONS, (
            "Most people never need to change these. Changing them makes eyeokuri learn your usual "
            "eye openness and head position again."))

    def _build_settings_tab(self, tab: ttk.Frame, sections: tuple[str, ...], note: str) -> None:
        ttk.Label(tab, foreground=theme.MUTED, wraplength=640, justify="left", text=note).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        row = 1
        for section in sections:
            values = self.general[section]
            ttk.Label(tab, text=section.capitalize(), font="TkHeadingFont").grid(
                row=row, column=0, sticky="w", pady=(8, 2))
            row += 1
            for key, value in values.items():
                if (section, key) in _HIDDEN_GENERAL:
                    continue
                ttk.Label(tab, text=key).grid(row=row, column=0, sticky="w", padx=(12, 8))
                if isinstance(value, bool):
                    bvar = tk.BooleanVar(value=value)
                    ttk.Checkbutton(tab, variable=bvar, command=lambda s=section, k=key, v=bvar: self._on_general_bool(
                        s, k, v.get())).grid(row=row, column=1, sticky="w")
                    self.general_vars.append(bvar)
                else:
                    svar = tk.StringVar(value=fmt(value) if isinstance(value, float) else str(value))
                    svar.trace_add("write", lambda *_a, s=section, k=key, v=svar, t=type(value): self._on_general_text(
                        s, k, v.get(), t))
                    ttk.Entry(tab, textvariable=svar, width=10).grid(row=row, column=1, sticky="w")
                    self.general_vars.append(svar)
                    if (section, key) == ("camera", "index"):
                        ttk.Button(tab, text="Choose from live views…",
                                   command=lambda v=svar: self._pick_camera(v)).grid(row=row, column=2, sticky="w")
                help_text = _GENERAL_HELP.get((section, key))
                if help_text:
                    ttk.Label(tab, text=help_text, foreground=theme.MUTED, wraplength=380, justify="left").grid(
                        row=row, column=3 if (section, key) == ("camera", "index") else 2,
                        sticky="w", padx=(8, 0))
                row += 1

    def _pick_camera(self, var: tk.StringVar) -> None:
        if self.camera_picker is not None and self.camera_picker.win.winfo_exists():
            self.camera_picker.win.lift()
            return
        # The view shown for "in use" is the running camera, not necessarily the edited index.
        running = self.app.config.camera.index
        self.camera_picker = CameraPicker(self.win, self.app, running, lambda i: var.set(str(i)))

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

    def _apply(self) -> None:
        """Puts valid edits in use; invalid ones wait until you fix them."""
        if self._apply_id is not None:
            self.win.after_cancel(self._apply_id)
            self._apply_id = None
        try:
            config = self.build_config()
        except ValueError:
            return
        if config != self.app.config:
            self.app.apply_config(config)

    def ok(self) -> None:
        """Saves and closes; if saving fails, the window stays open with your edits."""
        try:
            config = self.build_config()
            self.app.save_config(config)
        except (ValueError, OSError) as e:
            self.message.configure(text=str(e), foreground=theme.BAD)
            return
        self._close()

    def cancel(self) -> None:
        """Goes back to the settings in use when the window opened, and closes."""
        if self.app.config != self._opened_with:
            self.app.apply_config(self._opened_with)
        self._close()

    def _close_box(self) -> None:
        """The window's close button cancels, but asks first so one click can't undo your tuning."""
        try:
            changed = self.build_config() != self._opened_with
        except ValueError:
            changed = True
        if changed and not messagebox.askyesno(
                "eyeokuri settings", "Discard your changes?", icon="warning", parent=self.win):
            return
        self.cancel()

    def use_fit(self, name: str, gesture: GestureConfig, takes: list[Take]) -> None:
        """Puts the wizard's result in the editor and applies it."""
        self.gestures[name] = gesture_model(gesture)
        self._select(name)
        self._apply()

    def _close(self) -> None:
        if self._apply_id is not None:
            self.win.after_cancel(self._apply_id)
        if self.app.wizard is not None and self.app.wizard.settings is self:
            self.app.wizard.close()
        if self.camera_picker is not None and self.camera_picker.win.winfo_exists():
            self.camera_picker.close()
        self.app.settings = None
        self.app.push_config()
        self.win.destroy()
