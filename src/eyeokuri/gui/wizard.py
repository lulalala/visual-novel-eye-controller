"""The gesture wizard: records takes, fits the gesture to them and offers the result."""

from __future__ import annotations

import time
import tkinter as tk
from dataclasses import replace
from tkinter import ttk
from typing import TYPE_CHECKING

from eyeokuri import theme
from eyeokuri.config import GestureConfig
from eyeokuri.eyes import Observation
from eyeokuri.gui.model import gesture_model, wizard_traces
from eyeokuri.gui.plot import PlotEditor, tint
from eyeokuri.gui.tkutil import place_over, scaled_font
from eyeokuri.gui.worker import MAX_TAKE_S
from eyeokuri.triggers import Replay, signal_value
from eyeokuri.tuning import DO, KIND_LABELS, TOO_QUICK, TOO_SLOW, Fit, Take, fit, script, trim

if TYPE_CHECKING:
    from eyeokuri.gui.gesture_window import GestureWindow
    from eyeokuri.gui.main_window import MainWindow


# Near misses you might still want to count, so the wizard asks instead of assuming.
_ASK_KINDS = (TOO_QUICK, TOO_SLOW)
_WIZARD_WRAP = 760


def _outcome(kind: str) -> str:
    return "you choose" if kind in _ASK_KINDS else "should fire" if kind == DO else "shouldn't fire"


class WizardWindow:
    """Sets up the gesture window's gesture step by step: one page per take,
    each with one thing to do, then a review of the gesture fitted to all the
    takes. The result goes back to the gesture window, whose OK saves it.

    The gesture window only offers the wizard when its edits are valid and
    every step has a box (``can_tune``)."""

    def __init__(self, app: MainWindow, owner: GestureWindow) -> None:
        self.app = app
        self.owner = owner
        self.worker = app.worker
        self.base = owner.build_config()
        self.name = owner.name
        self.script = script(self.name)
        self.takes: list[Take | None] = [None] * len(self.script)
        self.answers: dict[int, str] = {}
        """Your answer to "should this fire?" (DO or the near miss), by page."""
        self.fitted: Fit | None = None
        self.results: dict[int, Replay] = {}
        """The fitted gesture replayed over each recorded take, by page."""
        self.page = 0
        """One page per take, then the review."""
        self.enable = tk.BooleanVar(value=True)
        self._started: float | None = None
        self._poll_id: str | None = None

        parent = owner.win
        self.win = tk.Toplevel(parent)
        self.win.withdraw()
        self.win.title(f"Gesture wizard – {self.name}")
        self.win.transient(parent)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        # Gestures are off while you record, so your takes send nothing to other windows.
        self.worker.set_suspended(True)
        self._build()
        self._show(0)
        place_over(self.win, app.root)
        self.win.grab_set()
        self._poll()

    def _build(self) -> None:
        self._text = scaled_font("TkDefaultFont", 1.25)
        self._bold = scaled_font("TkHeadingFont", 1.25)
        self._big = scaled_font("TkHeadingFont", 1.8)
        style = ttk.Style(self.win)
        for widget in ("TLabel", "TButton", "TRadiobutton", "TCheckbutton"):
            style.configure(f"Wizard.{widget}", font=self._text)
        style.configure("Wizard.Treeview", font=self._text, rowheight=self._text.metrics("linespace") + 6)
        style.configure("Wizard.Treeview.Heading", font=self._bold)
        style.configure("Wizard.Accent.TButton", font=self._text)

        self.body = ttk.Frame(self.win, padding=16)
        self.body.pack(fill="both", expand=True)
        self.body.columnconfigure(0, weight=1)
        self.body.rowconfigure(3, weight=1)
        self.counter = ttk.Label(self.body, style="Wizard.TLabel", foreground=theme.MUTED)
        self.counter.grid(row=0, column=0, sticky="w")
        self.heading = ttk.Label(self.body, font=self._big, wraplength=_WIZARD_WRAP, justify="left")
        self.heading.grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.subheading = ttk.Label(self.body, style="Wizard.TLabel", wraplength=_WIZARD_WRAP, justify="left")
        self.subheading.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.content = ttk.Frame(self.body)
        nav = ttk.Frame(self.body)
        nav.grid(row=4, column=0, sticky="ew", pady=(16, 0))
        ttk.Button(nav, text="Cancel", style="Wizard.TButton", command=self.close).pack(side="left")
        self.next_button = ttk.Button(nav, style="Wizard.Accent.TButton", command=self._next)
        self.next_button.pack(side="right")
        self.back_button = ttk.Button(nav, text="Back", style="Wizard.TButton",
                                      command=lambda: self._show(self.page - 1))
        self.back_button.pack(side="right", padx=6)

    def _gesture(self) -> GestureConfig:
        return self.fitted.gesture if self.fitted else self.base.gestures[self.name]

    def _kind(self, page: int) -> str:
        return self.answers.get(page, self.script[page][0])

    def _on_review(self) -> bool:
        return self.page == len(self.script)

    def _on_take(self) -> bool:
        return 0 <= self.page < len(self.script)

    # Pages

    def _show(self, page: int) -> None:
        # A take you leave while recording is dropped; the one before it stays.
        self._started = None
        self.content.destroy()
        self.content = ttk.Frame(self.body)
        self.content.grid(row=3, column=0, sticky="nsew", pady=(14, 0))
        self.page = page
        if self._on_take():
            self._take_page()
        else:
            self._review_page()

    def _next(self) -> None:
        if self._on_review():
            self._use()
        else:
            self._show(self.page + 1)

    def _take_page(self) -> None:
        kind, what = self.script[self.page]
        self.counter.configure(text=f"Take {self.page + 1} of {len(self.script)}")
        self.heading.configure(text=f"{what[0].upper()}{what[1:]}.")
        outcome = "" if kind in _ASK_KINDS else _outcome(kind).capitalize() + "."
        # The first page also says what the wizard does, since it has no page of its own.
        intro = f"Record a few takes, and the wizard fits {self.name} to them. " if self.page == 0 else ""
        self.subheading.configure(text=intro + outcome)
        row = ttk.Frame(self.content)
        row.pack(fill="x")
        self.record_button = ttk.Button(row, width=12, style="Wizard.TButton", command=self._toggle_record)
        self.record_button.pack(side="left")
        self.status = ttk.Label(row, font=self._bold)
        self.status.pack(side="left", padx=(12, 0))
        if kind in _ASK_KINDS:
            ask = ttk.Frame(self.content)
            ask.pack(fill="x", pady=(10, 0))
            ttk.Label(ask, text="Should this fire?", style="Wizard.TLabel").pack(side="left")
            self.answer = tk.StringVar(value=self.answers.get(self.page, ""))
            for value, text in ((DO, "Yes"), (kind, "No")):
                ttk.Radiobutton(ask, text=text, value=value, variable=self.answer, style="Wizard.TRadiobutton",
                                command=self._on_answer).pack(side="left", padx=(10, 0))
        self.plot = PlotEditor(self.content, lambda _i, _k, _v: None)
        self.plot.canvas.pack(fill="both", expand=True, pady=(12, 0))
        self.result = ttk.Label(self.content, style="Wizard.TLabel", wraplength=_WIZARD_WRAP, justify="left")
        self.result.pack(anchor="w", pady=(8, 0))
        # The focused button takes Space, so you can record without the mouse.
        self.record_button.focus_set()
        self._refresh_take()

    def _on_answer(self) -> None:
        self.answers[self.page] = self.answer.get()
        take = self.takes[self.page]
        if take is not None:
            self.takes[self.page] = replace(take, kind=self.answers[self.page])
            self._refit()
        self._refresh_take()

    def _refresh_take(self) -> None:
        planned = self.script[self.page][0]
        kind = self._kind(self.page)
        take = self.takes[self.page]
        recording = self._started is not None
        # The loud button is the one to press next: Record until there is a take, then Next.
        self.record_button.configure(text="■ Stop" if recording else "● Redo" if take else "● Record",
                                     style="Wizard.TButton" if take else "Wizard.Accent.TButton")
        state = "disabled" if recording else "normal"
        self.back_button.configure(state="disabled" if recording or self.page == 0 else "normal")
        answered = planned not in _ASK_KINDS or self.page in self.answers
        if take is None and planned != DO:
            self.next_button.configure(text="Skip", state=state, style="Wizard.TButton")
        else:
            ready = take is not None and answered and not recording
            self.next_button.configure(text="Next", state="normal" if ready else "disabled",
                                       style="Wizard.Accent.TButton" if ready else "Wizard.TButton")
        if recording or take is None:
            self.result.configure(text="")
        elif not answered:
            self.result.configure(text="Choose Yes or No.", foreground=theme.TRACE)
        else:
            result = self.results[self.page]
            fired = result.fired_at is not None
            ok = fired == (kind == DO)
            if fired:
                text = "Fires, as it should." if ok else "Fires, but it shouldn't."
            else:
                text = f"Doesn't fire{', as it should' if ok else ''}: {result.reason}."
            message = f"{'✓' if ok else '✕'} {text}"
            if kind == DO and not self._moved(take):
                message += " Hardly any movement: redo it and move further."
            elif not ok:
                message += " Redo it if you got it wrong."
            self.result.configure(text=message, foreground=theme.OK if ok else theme.BAD)
        self._draw(self.page)

    def _review_page(self) -> None:
        self.counter.configure(text="Review")
        self.heading.configure(text=f"New settings for {self.name}")
        self.subheading.configure(text="Select a take to see it on the plot.")
        self.content.columnconfigure(1, weight=1)
        self.content.rowconfigure(0, weight=1)
        left = ttk.Frame(self.content)
        left.grid(row=0, column=0, sticky="ns")
        view = self.take_list = ttk.Treeview(left, columns=("take", "result"), show="headings",
                                             height=8, selectmode="browse", style="Wizard.Treeview")
        view.heading("take", text="Take")
        view.heading("result", text="Result")
        view.column("take", width=170)
        view.column("result", width=340)
        view.tag_configure("ok", foreground=theme.OK)
        view.tag_configure("bad", foreground=theme.BAD)
        view.bind("<<TreeviewSelect>>", lambda _e: self._draw(self._picked()))
        view.pack(fill="y", expand=True)
        ttk.Button(left, text="Redo take", style="Wizard.TButton", command=self._redo).pack(anchor="w", pady=(4, 0))
        self.plot = PlotEditor(self.content, lambda _i, _k, _v: None)
        self.plot.canvas.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        recorded = [j for j, t in enumerate(self.takes) if t is not None]
        wrong = 0
        for j in recorded:
            take, result = self.takes[j], self.results[j]
            assert take is not None
            fired = result.fired_at is not None
            ok = fired == (take.kind == DO)
            wrong += not ok
            text = "fires" if fired else f"doesn't fire: {result.reason}"
            # Numbered by page, as on the take pages and in the notes below.
            view.insert("", "end", iid=str(j), values=(f"{j + 1}. {KIND_LABELS[take.kind].capitalize()}",
                        f"{'✓' if ok else '✕'} {text}"), tags=("ok" if ok else "bad",))
        row = 1
        if self.fitted is not None:
            # The verdict first, then what to act on, then what changed.
            summary = ("Every take does what it should." if not wrong else
                       f"{wrong} take(s) don't do what they should. Redo them, or fine-tune the boxes afterward.")
            changes = self.fitted.changes or ["Your takes fit the current settings. Nothing changed."]
            for lines, color in (([summary], theme.OK if not wrong else theme.BAD),
                                 ([f"• {w}" for w in self.fitted.warnings], theme.BAD),
                                 ([f"• {c}" for c in changes], None)):
                if lines:
                    ttk.Label(self.content, style="Wizard.TLabel", wraplength=_WIZARD_WRAP, justify="left",
                              text="\n".join(lines), **({"foreground": color} if color else {}),
                              ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10 if row == 1 else 6, 0))
                    row += 1
        if not self.base.gestures[self.name].enabled:
            ttk.Checkbutton(self.content, text=f"Turn {self.name} on", variable=self.enable, style="Wizard.TCheckbutton",
                            ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.back_button.configure(state="normal")
        has_do = any(t is not None and t.kind == DO for t in self.takes)
        self.next_button.configure(text="Use these settings", state="normal" if has_do else "disabled",
                                   style="Wizard.Accent.TButton")
        self.next_button.focus_set()
        if recorded:
            view.selection_set(str(recorded[0]))
        self._draw(self._picked())

    def _picked(self) -> int | None:
        sel = self.take_list.selection()
        return int(sel[0]) if sel else None

    def _redo(self) -> None:
        picked = self._picked()
        if picked is not None:
            self._show(picked)

    # Recording

    def _toggle_record(self) -> None:
        if self._started is None:
            self._started = time.monotonic()
        else:
            elapsed = time.monotonic() - self._started
            self._started = None
            observations = self.worker.recent(elapsed)
            if observations:
                self.takes[self.page] = Take(self._kind(self.page), observations)
                self._refit()
        self._refresh_take()

    def _poll(self) -> None:
        if self._on_take():
            problem = self._face_problem()
            take = self.takes[self.page]
            if self._started is not None:
                elapsed = time.monotonic() - self._started
                if elapsed >= MAX_TAKE_S:
                    self._toggle_record()
                else:
                    self._draw(self.page, self.worker.recent(elapsed))
                    text = f"Recording… {elapsed:.1f} s" + (f"   ({problem})" if problem else "")
                    self.status.configure(text=text, foreground=theme.BAD if problem else theme.OK)
            elif problem:
                self.status.configure(text=problem[0].upper() + problem[1:], foreground=theme.BAD)
            elif take is not None:
                self.status.configure(text=f"Recorded {take.observations[-1].timestamp:.1f} s", foreground=theme.MUTED)
            else:
                self.status.configure(text="Ready (Space starts and stops)", foreground=theme.MUTED)
        self._poll_id = self.win.after(100, self._poll)

    def _face_problem(self) -> str | None:
        if self.worker.engine is None:
            return "the camera isn't running"
        recent = self.worker.recent(0.3)
        signals = {s.signal for s in self.base.gestures[self.name].steps}
        if not recent or any(signal_value(s, recent[-1]) is None for s in signals):
            return "no face in view"
        return None

    def _moved(self, take: Take) -> bool:
        signals = {s.signal for s in self.base.gestures[self.name].steps}
        return trim(take.observations, signals)[1] is not take.observations

    # Fitting

    def _refit(self) -> None:
        recorded = [(j, t) for j, t in enumerate(self.takes) if t is not None]
        self.fitted = fit(self.base, self.name, [t for _, t in recorded], [j + 1 for j, _ in recorded]) if recorded else None
        self.results = {} if self.fitted is None else {
            j: r for (j, _), r in zip(recorded, self.fitted.results)}

    def _draw(self, picked: int | None, live: list[Observation] | None = None) -> None:
        # While recording, the plot shows the raw signal as it comes in.
        signals = {s.signal for s in self._gesture().steps if s.signal}
        traces = wizard_traces(self.takes, self.results, picked, signals, self._on_review(), live)
        tones = {"ok": tint(theme.OK, 0.45), "bad": tint(theme.BAD, 0.45), "plain": theme.GRID_TRACE}
        others = [(cut, tones[tone]) for cut, tone in traces.others]
        self.plot.draw(gesture_model(self._gesture()), traces.main, traces.result, traces.duration, others,
                       traces.boxes)

    def _use(self) -> None:
        assert self.fitted is not None
        gesture = replace(self.fitted.gesture, enabled=self.fitted.gesture.enabled or self.enable.get())
        owner = self.owner
        takes = [t for t in self.takes if t is not None]
        self.close()
        owner.use_fit(gesture, takes)

    def close(self) -> None:
        if self._poll_id is not None:
            self.win.after_cancel(self._poll_id)
        self.app.wizard = None
        self.app.push_config()
        self.win.grab_release()
        self.win.destroy()
