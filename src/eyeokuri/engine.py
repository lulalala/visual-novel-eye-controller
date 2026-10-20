"""Runs the pipeline one frame at a time: source signals -> eye and head state -> gestures -> output."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from eyeokuri.config import Config
from eyeokuri.eyes import EyeStateTracker, Observation
from eyeokuri.feedback import play_sound
from eyeokuri.head import HeadTracker
from eyeokuri.outputs import (
    APP_OUTPUTS, APP_PREFIX, ActionDispatcher, Output, check_output_name, create_output,
)
from eyeokuri.pause import PauseSwitch
from eyeokuri.sources import Source
from eyeokuri.triggers import Trigger, TriggerEvent, create_triggers, supported_triggers


def validate_outputs(config: Config) -> None:
    for name, gesture in config.gestures.items():
        output = gesture.output
        if output == "":
            continue
        if output.startswith(APP_PREFIX):
            if output not in APP_OUTPUTS:
                raise ValueError(
                    f"gestures.{name}.output: unknown app output {output!r}; "
                    f"choose from {', '.join(sorted(APP_OUTPUTS))}"
                )
        else:
            try:
                check_output_name(output)
            except ValueError as e:
                raise ValueError(
                    f"gestures.{name}.output: {e}; mouse outputs are left_click, right_click, "
                    "wheel_down, and \"\" sends nothing"
                ) from None


def check_config(config: Config) -> None:
    """Raises ValueError for settings that would fail later, before the camera opens."""
    validate_outputs(config)
    EyeStateTracker(config.eyes)
    HeadTracker(config.head)
    create_triggers(config)


@dataclass(frozen=True)
class Frame:
    obs: Observation
    fired: bool
    """True if a gesture sent keyboard or mouse input this frame."""


class Engine:
    """Owns the source, trackers, gestures and outputs. The command line loop
    and the GUI both drive it by calling step() once per frame.

    set_config(), toggle_pause() and set_suspended() may be called from
    another thread: they take effect at the start of the next step().

    Suspended means the front end is using the signals itself (editing
    settings, recording takes): the pipeline keeps producing observations,
    but gestures neither match nor send anything. Unlike pause, no gesture
    can end it.
    """

    def __init__(
        self,
        config: Config,
        log: Callable[[str], None],
        source: Source | None = None,
        output: Output | None = None,
        sound: Callable[[str], None] = play_sound,
    ) -> None:
        self._log = log
        self._sound = sound
        self._own_source = source is None
        self._own_output = output is None
        if source is None:
            from eyeokuri.sources.opencv import OpenCVSource

            source = OpenCVSource(config.camera, log)
        self.source = source
        self._output = output
        self.pause = PauseSwitch(self._on_pause_change)
        self.fps = 0.0
        self.last_fire_at = -1e9
        self._prev: float | None = None
        self._pending: Config | None = None
        self._pause_requested = False
        self._suspend_requested: bool | None = None
        self.suspended = False
        self.config: Config | None = None
        self._apply(config)

    def set_config(self, config: Config) -> None:
        self._pending = config

    def toggle_pause(self) -> None:
        self._pause_requested = True

    def set_suspended(self, suspended: bool) -> None:
        self._suspend_requested = suspended

    @property
    def paused(self) -> bool:
        return self.pause.paused

    def statuses(self) -> list[str]:
        return [f"{t.name}: {t.status()}" for t in self.triggers]

    def _apply(self, config: Config) -> None:
        old = self.config
        self.config = config
        if old is not None and self._own_source and config.camera != old.camera:
            from eyeokuri.sources.opencv import OpenCVSource

            self.source.close()
            self.source = OpenCVSource(config.camera, self._log)
        # A new tracker learns your open-eye level and usual pose again, so
        # keep the old ones unless their settings changed.
        if old is None or config.eyes != old.eyes:
            self.eyes = EyeStateTracker(config.eyes)
        if old is None or config.head != old.head:
            self.head = HeadTracker(config.head)
        log_rejected = self._log if config.feedback.log_rejected else None
        self.triggers: list[Trigger] = supported_triggers(
            create_triggers(config, log_rejected), self.source, self._log
        )
        if self._own_output and self._output is None:
            self._output = create_output(self._log)
        self._outputs = {name: g.output for name, g in config.gestures.items()}
        # App-level outputs (app:*) are handled in step(); only keystroke and
        # mouse outputs go to ActionDispatcher.
        key_actions = {k: v for k, v in self._outputs.items() if v and not v.startswith(APP_PREFIX)}
        assert self._output is not None
        self.dispatcher = ActionDispatcher(self._output, key_actions, self._on_fire)

    def _on_fire(self, event: TriggerEvent, output_name: str) -> None:
        self.last_fire_at = event.timestamp
        self._log(f"{event.trigger}: {event.detail} -> {output_name}")
        assert self.config is not None
        if self.config.feedback.sound:
            self._sound("trigger")

    def _on_pause_change(self, paused: bool) -> None:
        self._log("Paused" if paused else "Resumed")
        assert self.config is not None
        if self.config.feedback.sound:
            self._sound("pause" if paused else "resume")

    def step(self) -> Frame:
        pending, self._pending = self._pending, None
        if pending is not None:
            self._apply(pending)
        if self._pause_requested:
            self._pause_requested = False
            self.pause.toggle()
        requested, self._suspend_requested = self._suspend_requested, None
        if requested is not None and requested != self.suspended:
            self.suspended = requested
            # Gestures didn't see the frames in between, so none may carry over.
            for trigger in self.triggers:
                trigger.reset()
            self._log("Gestures off" if requested else "Gestures on")

        signals = self.source.read()
        now = signals.timestamp
        if self._prev is not None:
            self.fps = 0.9 * self.fps + 0.1 * (1.0 / max(now - self._prev, 1e-6))
        self._prev = now

        head_yaw, head_pitch = self.head.update(signals)
        obs = replace(self.eyes.update(signals), head_yaw=head_yaw, head_pitch=head_pitch)

        fired = False
        for trigger in () if self.suspended else self.triggers:
            event = trigger.update(obs)
            if event is None:
                continue
            mapped = self._outputs.get(event.action)
            if not mapped:
                # Only a step of other gestures.
                self._log(f"{event.trigger}: {event.detail}")
                continue
            if mapped.startswith(APP_PREFIX):
                self._log(f"{event.trigger}: {event.detail}")
                if mapped == "app:toggle_pause":
                    self.pause.toggle()
                continue
            if self.pause.paused:
                # Log what would have been sent, so you can try gestures while paused.
                self._log(f"{event.trigger}: {event.detail} -> {mapped} (paused, not sent)")
                continue
            fired = self.dispatcher.dispatch(event) or fired
        return Frame(obs, fired)

    def close(self) -> None:
        if self._own_source:
            self.source.close()
