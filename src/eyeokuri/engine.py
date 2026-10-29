"""Runs the pipeline one frame at a time: source signals -> eye and head state -> gestures -> output."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from eyeokuri.config import Config
from eyeokuri.eyes import EyeStateTracker, Observation
from eyeokuri.feedback import play_sound
from eyeokuri.head import HeadTracker
from eyeokuri.outputs import (
    APP_OUTPUTS, MOUSE_BUTTONS, MOUSE_OUTPUTS, OUTPUT_MODES, Output, check_output_name, create_output, pressed_by,
)
from eyeokuri.pause import PauseSwitch
from eyeokuri.sources import Source
from eyeokuri.triggers import Trigger, TriggerEvent, create_triggers, supported_triggers


def validate_outputs(config: Config) -> None:
    for name, gesture in config.gestures.items():
        output, mode = gesture.output, gesture.output_mode
        if mode not in OUTPUT_MODES:
            raise ValueError(f"gestures.{name}.output_mode must be one of {', '.join(OUTPUT_MODES)}, not {mode!r}")
        if output != "" and output not in APP_OUTPUTS:
            try:
                check_output_name(output)
            except ValueError as e:
                raise ValueError(
                    f"gestures.{name}.output: {e}; mouse outputs are {', '.join(MOUSE_OUTPUTS)}, "
                    f"app outputs are {', '.join(sorted(APP_OUTPUTS))}, and \"\" sends nothing"
                ) from None
        if mode != "press" and not _can_hold(output):
            raise ValueError(
                f"gestures.{name}.output_mode {mode} needs a key, key combination, "
                f"{' or '.join(MOUSE_BUTTONS)} as the output, not {output!r}"
            )
    _check_held_outputs_are_not_shared(config)


def _can_hold(output: str) -> bool:
    return output in MOUSE_BUTTONS or not (output == "" or output in APP_OUTPUTS or output in MOUSE_OUTPUTS)


def _check_held_outputs_are_not_shared(config: Config) -> None:
    """Letting go of a key that another output also uses would end that output's
    press or hold early, so a held key belongs to one enabled gesture only."""
    sending = {n: g for n, g in config.gestures.items()
               if g.enabled and g.output != "" and g.output not in APP_OUTPUTS}
    for name, gesture in sending.items():
        if gesture.output_mode == "press":
            continue
        held = pressed_by(gesture.output)
        for other, other_gesture in sending.items():
            shared = held & pressed_by(other_gesture.output)
            if other != name and shared:
                raise ValueError(
                    f"gestures.{name} holds {', '.join(sorted(shared))} down, so gestures.{other}.output "
                    f"can't use it too ({other_gesture.output!r}); pick outputs without shared keys"
                )


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
    another thread: they take effect at the start of the next step(). Settings
    that set_config() gets but that aren't valid are logged and not applied.

    Suspended means the front end is using the signals itself (editing
    settings, recording takes): the pipeline keeps producing observations,
    but gestures neither match nor send anything. Unlike pause, no gesture
    can end it.

    A held output (output_mode = "toggle" or "while") is down for the whole
    system, not just the game, so the engine lets go of it on pause, suspend,
    new settings, face loss and close() as well as when the gesture fires
    again (toggle) or ends (while).
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
        # Outputs that toggle and while gestures hold down, in the order they went down.
        self._held: list[str] = []
        # Only read here: afterwards the engine owns the paused state, and
        # set_config() leaves it alone.
        self.pause = PauseSwitch(self._on_pause_change, paused=config.app.paused)
        # What each of outputs.APP_OUTPUTS does.
        self.app_actions: dict[str, Callable[[], None]] = {"app_pause_toggle": self.pause.toggle}
        self.fps = 0.0
        self.last_fire_at = -1e9
        self._prev: float | None = None
        self._pending: Config | None = None
        self._pause_requested = False
        self._suspend_requested: bool | None = None
        self.suspended = False
        self.config: Config | None = None
        self._apply(config)
        if self.pause.paused:
            self._log("Starting paused (app.paused): gestures send nothing until you resume")

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
        # Checked before anything changes, so bad settings leave the engine as it was.
        check_config(config)
        # The gesture that held an output might now send something else.
        self._release_held("settings changed")
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
        self._modes = {name: g.output_mode for name, g in config.gestures.items()}

    def _release_held(self, reason: str) -> None:
        while self._held:
            name = self._held.pop()
            assert self._output is not None
            self._output.up(name)
            self._log(f"Released {name}: {reason}")

    def _on_fire(self, event: TriggerEvent, output_name: str) -> None:
        self.last_fire_at = event.timestamp
        self._log(f"{event.trigger}: {event.detail} -> {output_name}")
        assert self.config is not None
        if self.config.feedback.sound:
            self._sound("trigger")

    def _on_pause_change(self, paused: bool) -> None:
        self._log("Paused" if paused else "Resumed")
        if paused:
            self._release_held("paused")
        assert self.config is not None
        if self.config.feedback.sound:
            self._sound("pause" if paused else "resume")

    def step(self) -> Frame:
        pending, self._pending = self._pending, None
        if pending is not None:
            try:
                self._apply(pending)
            except ValueError as e:
                # From another thread, so raising would stop the engine; keep the settings in use.
                self._log(f"Settings not applied: {e}")
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
            if requested:
                self._release_held("gestures off")

        signals = self.source.read()
        now = signals.timestamp
        if self._prev is not None:
            self.fps = 0.9 * self.fps + 0.1 * (1.0 / max(now - self._prev, 1e-6))
        self._prev = now

        head_yaw, head_pitch, head_roll = self.head.update(signals)
        obs = replace(self.eyes.update(signals), head_yaw=head_yaw, head_pitch=head_pitch, head_roll=head_roll)
        if not obs.face_present:
            # Nobody is there to fire the gesture again and let go.
            self._release_held("no face")

        fired = False
        for trigger in () if self.suspended else self.triggers:
            event = trigger.update(obs)
            if event is not None:
                fired = self._handle(event) or fired
        return Frame(obs, fired)

    def _handle(self, event: TriggerEvent) -> bool:
        """Acts on a gesture that fired or ended. True if it fired and sent keyboard or mouse input."""
        mapped = self._outputs.get(event.action)
        mode = self._modes.get(event.action)
        if event.ended:
            # Only a while gesture acts on its end. It's already up if a pause,
            # suspend or lost face let go of it first.
            if mode == "while" and mapped in self._held:
                assert self._output is not None
                self._held.remove(mapped)
                self._output.up(mapped)
                self._log(f"{event.trigger}: {event.detail} -> {mapped} released")
            return False
        if not mapped or mapped in APP_OUTPUTS:
            # No output: only a step of other gestures. Otherwise an app-level output.
            self._log(f"{event.trigger}: {event.detail}")
            if mapped:
                self.app_actions[mapped]()
            return False
        if self.pause.paused:
            # Log what would have been sent, so you can try gestures while paused.
            self._log(f"{event.trigger}: {event.detail} -> {mapped} (paused, not sent)")
            return False
        assert self._output is not None
        if mode == "press":
            self._output.send(mapped)
            self._on_fire(event, mapped)
        elif mapped not in self._held:
            self._output.down(mapped)
            self._held.append(mapped)
            self._on_fire(event, f"{mapped} held")
        elif mode == "toggle":
            self._held.remove(mapped)
            self._output.up(mapped)
            self._on_fire(event, f"{mapped} released")
        else:
            # A while gesture that fires again before it ended keeps holding.
            return False
        return True

    def close(self) -> None:
        self._release_held("stopping")
        if self._own_source:
            self.source.close()
