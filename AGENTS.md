# AGENTS.md

`eyeokuri` lets someone reading a visual novel advance the text hands-free: it watches a webcam, detects face gestures (blink, head shake, nod) and sends a key or mouse input (`Enter` by default) to the foreground window. Users are visual novel readers on **Windows**, which is also where development and testing happen. Stage 2 (working prototype) is current; research is in `docs/research.md`, the file layout in `docs/development.md`.

## Hard rules

- **Privacy.** Camera frames stay in memory and are never written to disk or sent anywhere. `--log` writes numbers only. Don't add features that save frames, upload data or make network calls; the one exception is the existing one-time face model download. This is the project's main promise to users.
- Don't use the `mediapipe` package (it includes telemetry); the face model runs through OpenCV DNN.
- No new runtime dependencies, and no linter, formatter or type checker, unless the user asks.
- Only commit or push when the user asks. Don't build on or merge the `gui-wip` branch (an abandoned PySide6 GUI).

## Design rules

1. **Gestures are config, not code.** Each `[gestures.NAME]` section lists steps and an `output`; the event is named after the gesture. Trigger code never chooses an output.
   - A step is a box on a plot of one signal over time: a value range (`above_ratio`/`below_ratio` for eyes, `above_deg`/`below_deg` for head) plus time since the previous step (`after_min_s`/`after_max_s`) and an optional `hold_s`. It counts the frame the signal enters the box. A step can instead name another gesture; `create_triggers` builds gestures after the ones they use, and triggers must update in that order.
   - Every setting belongs to one step, so changing it never affects another step or gesture. Hysteresis is two boxes (a nod enters past 12° and returns inside ±8°).
   - When one movement matches several gestures, each fires. No arbitration.
   - Each step maps to one box and each limit to one draggable edge in the GUI plot. Keep new step fields drawable that way.
2. Outputs are a key name from `KEY_VK` (optionally with modifiers, `ctrl+s`), a `MOUSE_OUTPUTS` name, or an `app:` output (only `app:toggle_pause`), which `Engine.step()` handles itself: a new one goes in `APP_OUTPUTS` with its action in `Engine.app_actions`.
3. Triggers are pure state machines: `Observation` in, `TriggerEvent | None` out. No camera, OS or wall-clock access; use `obs.timestamp` only, so they stay testable.
4. A trigger that loses the face (`not obs.face_present` or a `None` head value) must `reset()` and cancel any half-done gesture.
5. Head signs: **positive pitch = head tilted down**, **positive yaw = your left**. Easy to get backwards; `signal_value` in `triggers.py` is the reference.
6. Config precedence: defaults < `--config` file < shortcut flags < `--set SECTION.KEY=VALUE`. `--set` reaches one step by index (`gestures.blink.steps.1.after_min_s=0.4`).
7. Config files must have `version = 1` (`CONFIG_VERSION`); others are rejected, not migrated. Bump it when a change would make old files mean something else.
8. New pipeline behavior goes in `Engine`, not in `app.py` or `gui/`, because both front ends drive the same engine.

## GUI rules

- Only the main thread touches Tk widgets. The worker thread runs `Engine`; the main thread polls it for frames and log lines. `Engine.set_config()` and `toggle_pause()` are the only calls safe from the main thread.
- Editor windows (gesture, config, wizard) edit a working copy and apply it live with `Engine.set_config()`; OK saves with `dump_config()`, Cancel restores what was in use when the window opened. Only one is open at a time, and gestures are suspended while it is.
- `app.paused` is read only at startup; `set_config()` must not change the live paused state.
- The gesture window gets match results from `triggers.replay()`, and the wizard fits limits with `tuning.fit()`. Don't reimplement matching or fitting in a window.
- Logic that needs no widgets goes in `gui/model.py` or `tuning.py` (no Tk imports), so it is unit-tested. One window per module; windows import `MainWindow` only under `TYPE_CHECKING`.
- **Translations.** Wrap every new user-facing GUI string with `_()` (`N_()` in module-level constants) following the rules in `docs/i18n/gui-plan.md`, and add the entry to every catalog in `locales/` in the same change. Log lines and `ValueError` messages stay English.
- **Layout: align to columns.** Rows that belong together share one grid so their entries line up (head limits use the steps table's columns). An add button sits directly under the column it extends. This is the most frequent correction in this repo.

## Code conventions

- Units go in names: `_s` seconds, `_deg` degrees, `_ratio` eye openness relative to the baseline.
- Validate config values in the constructor and raise `ValueError` naming the key and allowed values: `eyes.close_ratio must be above 0 and below eyes.open_ratio (0.75), not 0.9`.
- When a gesture is detected but doesn't fire, tell the user why through the trigger's `log` callback, shaped `"{name}: <what happened> (<reason>, <limit>)"`, e.g. `blink: step 2 came 0.12s after step 1 (too short, min 0.15s)`. Durations `.2f` s, angles whole degrees with `°`. Use `print` via `log`, never the `logging` module.
- Interfaces are `typing.Protocol`; concrete classes don't inherit from them.
- Import platform-specific code lazily inside the class that needs it (see `Win32Output`, `PynputOutput`).
- Use American English everywhere (code, comments, docs, commits).

## Checklists

**Add a built-in gesture** (no new trigger code needed for existing signals), all in one change:
1. An entry in `_default_gestures()` in `config.py`. Ask the user whether it starts enabled; there is no rule yet.
2. A matching section in `config.example.toml` with identical values (`test_example_config_matches_defaults` checks this).
3. The wizard's takes for it in `_SCRIPTS` in `tuning.py`: the gesture, and the near misses it should tell apart (`test_every_built_in_gesture_has_its_own_wizard_script` checks this). Add new prompt strings to every catalog in `locales/`.
4. Tests in `tests/test_triggers.py` driving synthetic 30 FPS `Observation` streams (`drive` helper): fires, each rejection reason, cooldown, face loss.
5. The site guide pages (`site/src/content/docs/guide/`, and every translated locale), if users see the change. The README only describes the app, how to install it and where the docs are, so change it only when those change.

**Add a signal:** a `SignalSpec` in `SIGNALS` in `config.py` (its unit, the source capability it needs, its rest value and the limits `tuning.fit()` keeps), `signal_value` in `triggers.py`, and a lane in `SIGNAL_PLOTS` in `gui/model.py`. A new unit also needs its bound fields in `StepConfig`.

**Add a key name:** its virtual-key code in `KEY_VK` (plus `EXTENDED_KEYS` if Windows sends it with `0xE0`); check `PynputOutput` finds it (rename in `_PYNPUT_NAMES` if needed) and `from_tk_event` maps its Tk keysym. **Add a mouse output:** `MOUSE_OUTPUTS`, implemented in both `Win32Output` and `PynputOutput`.

## Tests

Tests never use a real camera, face model, OS input or sound; build `Signals`/`Observation` objects or landmark arrays by hand. Plain `def test_*` functions with bare `assert`, named after behavior (`test_too_long_closure_is_canceled`). No test classes, no mocking framework.

## Docs

Follow the [developer documentation writing standard](https://github.com/NateBJones-Projects/developer-documentation-skill/blob/main/references/writing-standard.md). The rules agents most often miss:
- Address the reader as `you`; active voice, present tense, imperative for instructions. No `please`.
- `must` = requirement, `can` = available action, `might` = uncertain, `should` = clear recommendation only.
- Sentence-case headings. Task sections start with a verb ("Install the package"); concept sections are noun phrases.
- The README is a short front page; usage lives in the site guide, `docs/command-line.md` and `config.example.toml`. Don't copy guide text into the README. Docs for users give concrete numbers ("turn past ~15° to one side") and flag examples in step with the code.

## Git

- Subject: imperative, capitalized, no period, ≤ ~72 chars. Body: why, and what the user notices; bullets when several areas change; call out changed defaults.
- End with a `Co-Authored-By:` trailer for the model that wrote it.
- One logical change per commit.

## Definition of done

1. `.venv\Scripts\python -m pytest -q` passes, and new behavior has tests.
2. `.venv\Scripts\eyeokuri --help` and `.venv\Scripts\eyeokuri-gui --help` run without error.
3. Every new or changed config key has the same value in code defaults and `config.example.toml`, and works through `--set`.
4. The site guide pages, the README (if it is affected) and the Layout section of `docs/development.md` match the change.
5. The final message is 2–4 lines on what changed and what the user notices, then a list of what you could not test: real-camera behavior, real key output, and how GUI changes look. Never say a gesture "works" from unit tests; say it is unit-tested and needs a live check (`eyeokuri --preview` paused with `p`, then `eyeokuri` in a game).
