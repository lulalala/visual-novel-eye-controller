# AGENTS.md

Instructions for AI coding agents working in this repo. Read all of it before changing anything.

## Purpose

`vn-eye` lets someone reading a visual novel advance the text without touching the keyboard. It watches a webcam, detects face gestures (blink, head shake, head nod), and sends a key or mouse input (`Enter` by default) to the foreground window.

- Stage 1 (research) is done: see `docs/research.md`.
- Stage 2 (current): a working webcam prototype. Blink → `Enter` is the core feature. Head shake toggles pause.
- Main target platform: **Windows**. Development and testing happen mostly on **macOS** (MacBook built-in camera).

## Stack

- Python ≥ 3.11 (the local `.venv` uses 3.14). `src/` layout, package `vn_eye`, installed with `pip install -e ".[dev]"`.
- MediaPipe's Face Landmarker models (face detector + face mesh), run by OpenCV's DNN module. The `mediapipe` package is not used, because it includes telemetry. OpenCV also handles the camera and preview window. NumPy.
- `pynput`: key output on macOS/Linux. On Windows, key output uses `SendInput` through `ctypes` with hardware scan codes.
- Tests: `pytest` only. There is no linter, formatter or type checker set up. Don't add one unless asked.
- Config: TOML (`tomllib`), loaded into frozen dataclasses.

## Architecture

There is one pipeline. Each stage only talks to the next one:

```
sources/          Source.read()      → Signals (raw eye openness, head pose; frames stay inside the source)
                  OpenCVSource       (webcam → face_mesh.py: MediaPipe's face model run with OpenCV)
  → eyes.py       EyeStateTracker    (eye openness vs. a rolling open-eye baseline)
    head.py       HeadTracker        (yaw/pitch relative to a rolling median pose)
  → Observation                      (one per frame: timestamp, face_present, ready, closed, head_yaw, head_pitch)
  → triggers.py   StepWatcher        (the frame a signal enters one step's box)
                  GestureTrigger     → TriggerEvent (named after the gesture: steps matched in order)
  → engine.py     app:* events handled here (e.g. app:toggle_pause)
  → outputs.py    ActionDispatcher   → key/mouse output (each trigger has its own cooldown)
```

The design and the planned plugin loading are in `docs/design/sources.md`.

`Engine` (`engine.py`) owns the whole pipeline and advances it with `step()`, once per frame. Both front ends drive it: `app.py` (command line, OpenCV preview window, CSV log) and `gui.py` (Tkinter window). Put new pipeline behavior in `Engine`, not in a front end.

Other modules: `config.py` (dataclasses, TOML loading and `dump_config` for saving, overrides), `preview.py` (draws the state overlay on the source's `debug_view()`), `pause.py` (pause switch), `feedback.py` (sounds), `tuning.py` (fits a gesture's limits to labeled takes for the GUI wizard).

### GUI

- `gui.py` uses Tkinter only (no extra dependency). It runs `Engine` on a worker thread. Only the main thread touches Tk widgets: it polls the worker for the latest frame (as PPM bytes) and for log lines. `Engine.set_config()` and `toggle_pause()` are safe to call from the main thread; they apply at the next `step()`.
- The settings window edits a working copy, then calls `Engine.set_config()` on Apply and writes `dump_config()` on Save. It tests gestures with `triggers.replay()`, which runs the real matcher over recorded observations. Keep the editor's results coming from `replay()` instead of reimplementing the matching.
- Recorded tests hold `Observation`s (numbers) in memory only.
- The gesture wizard (`WizardWindow`) records a take between Record and Stop, has you label it (`tuning.DO`, `TOO_QUICK`, `TOO_SLOW`, `OTHER`), refits all takes with `tuning.fit()` after each change, and applies the result. Opened from the main window, it uses `MainWindow.config` and offers to save; opened from the settings window, it starts from that window's edits and hands the result back to it. Test recordings live in `MainWindow.tests`, so they last the session. It disables all gestures while open. `fit()` only moves limits a gesture already has (edges that leave rest, and nonzero time limits) and reports each take's result through `replay()`. Keep the fitting in `tuning.py`, which has no Tk code, so it stays unit-tested.
- The `gui-wip` branch (PySide6) is replaced by this; don't build on it.

### Rules the design depends on

1. **Gestures are config, not code.** Each `[gestures.NAME]` section (`Config.gestures`, a dict of `GestureConfig`) lists its steps and `output`. A gesture's event is named after the gesture. Trigger code never chooses an output; the only place outputs are chosen is `gestures.*.output`. Built-in gestures: `blink`, `head_shake`, `nod_up`, `nod_down`.
   - A step (`StepConfig`) is a box on a plot of one signal from `SIGNALS` over time: a value range (`above_ratio`/`below_ratio` for eyes, `above_deg`/`below_deg` for the head) and the time allowed since the previous step (`after_min_s`/`after_max_s`), plus an optional `hold_s`. It counts the frame the signal enters the box. A step can instead name another gesture (`gesture`), which counts when that gesture fires. `create_triggers` builds each gesture after the gestures it uses, and the app loop must update triggers in that order.
   - Every setting belongs to one step, so changing it never affects another step or gesture. Hysteresis is two boxes: a nod enters past 12° and returns inside ±8°. The eye openness signal is relative to the open-eye baseline; `[eyes] close_ratio`/`open_ratio` only decide what that baseline learns from and what the preview shows.
   - When the same movement matches several gestures, each one fires. There is no arbitration.
   - The config shape is meant for a plot-based editor: each step maps to one box, and each limit to one draggable edge. Keep new step fields drawable that way.
2. Outputs come in two kinds. Keystroke/mouse outputs are listed in `OUTPUT_NAMES` in `outputs.py` (`enter`, `space`, `left_click`, `wheel_down`, `up`, `down`). App-level outputs start with `app:` (currently only `app:toggle_pause`). The event loop in `app.py` handles `app:` outputs before `ActionDispatcher` sees them.
3. Triggers are pure state machines. They take an `Observation` and return a `TriggerEvent` or `None`. They must not touch the camera, the face model, the OS or wall-clock time. Use `obs.timestamp` only. This is what makes them testable.
4. A trigger that loses the face (`not obs.face_present`, or a `None` head value) must `reset()` and cancel any half-done gesture.
5. Head signs: **positive pitch = head tilted down** (image y grows downward), and **positive yaw = your left** (the face turns toward the unmirrored camera image's right). `signal_value` in `triggers.py` reads each signal.
6. Config precedence: defaults < `--config` file < shortcut flags (`--min-duration`, `--blink-key`, …) < `--set SECTION.KEY=VALUE`. `--set` reaches one step by index (`gestures.blink.steps.1.after_min_s=0.4`); a TOML list replaces all steps.
7. Config files must have `version = 1` (`CONFIG_VERSION`). Files without it are rejected, not migrated. Bump the version when a change would make old files mean something else.

## Privacy (hard rule)

Camera frames are processed in memory and are **never written to disk or sent anywhere**. `--log` writes numbers only (eye and head values per frame), never images. Do not add any feature that saves frames, uploads data or adds network calls. The one exception is the existing one-time download of the face landmark model.

## Conventions

### Code

- Every module starts with a one-line docstring saying what it does, then `from __future__ import annotations`.
- Type hints on every function signature. Use `X | None` and built-in generics (`list[str]`), not `Optional`/`List`.
- Config sections are `@dataclass(frozen=True)` with defaults in code. Each non-obvious field gets a comment above it that explains the behavior in user terms (for example `# Time allowed since the previous step. 0 means no limit.`).
- Interfaces are `typing.Protocol` (`Trigger`, `Output`). Concrete classes don't inherit from them.
- Units go in names: `_s` for seconds, `_deg` for degrees (`after_max_s`, `above_deg`), `_ratio` for eye openness relative to the baseline.
- Private state uses a leading underscore. Comments explain *why* or describe the gesture, not what the line does. Match the existing comment density, which is sparse.
- Validate config values that the type can't enforce in the constructor, and raise `ValueError` with a message that names the key and the allowed values. Example: `eyes.close_ratio must be above 0 and below eyes.open_ratio (0.75), not 0.9`.
- No new runtime dependencies without asking. Platform-specific code is imported lazily inside the class or function that needs it (see `Win32Output`, `PynputOutput`).

### User feedback and logging

- When a gesture is detected but doesn't fire, the user should be told why. Pass the optional `log` callback into the trigger and call it with a message shaped like `"{name}: <what happened> (<reason>, <limit>)"`. Example: `blink: step 2 came 0.12s after step 1 (too short, min 0.15s)`. Format durations as `.2f` seconds and angles as whole degrees with `°`.
- Use `print` through the `log` callback. Don't add the `logging` module.

### Adding a built-in gesture (checklist)

A gesture made of existing signals needs no new trigger code. Do all of these in the same change:

1. An entry in `_default_gestures()` in `config.py`. There is no fixed rule yet for whether a new gesture starts on or off, so ask the user before choosing `enabled`.
2. A matching `[gestures.NAME]` section in `config.example.toml`. The values there must equal the code defaults; `test_example_config_matches_defaults` checks this.
3. Tests in `tests/test_triggers.py` that drive the gesture with synthetic `Observation` streams at 30 FPS (see the `drive` helper). Cover at least: it fires, it doesn't fire (each rejection reason), cooldown, and face loss.
4. The README, if users can see the change (a new gesture, flag or default).

Adding a new signal: add it to `SIGNALS` in `config.py`, read it in `signal_value` in `triggers.py`, and give it bound fields with its unit in `StepConfig`. Include it in `GestureTrigger.needs`, so that a gesture is skipped at startup with a notice when the source doesn't provide the signal.

Adding a new output name: add it to `OUTPUT_NAMES` and implement it in **both** `Win32Output` (scan code, plus `KEYEVENTF_EXTENDEDKEY` for extended keys) and `PynputOutput`.

### Tests

- Tests never use a real camera, face model, OS input or sound. Build `Signals`/`Observation` objects (or landmark arrays) by hand.
- Use the plain `def test_*` function style with bare `assert`, and name tests after behavior (`test_too_long_closure_is_canceled`). No test classes and no mocking framework.

### Docs

Follow the [developer documentation writing standard](https://github.com/NateBJones-Projects/developer-documentation-skill/blob/main/references/writing-standard.md). Key rules:

- Address the reader as `you`. Use active voice, present tense, and imperative verbs for instructions.
- Use `must` for a requirement, `can` for an available action, and `might` for an uncertain outcome. Use `should` only for a clear recommendation.
- Do not use `please` in instructions. Remove filler and promotional claims.
- Use one term consistently for the same thing.
- Headings: sentence case, no skipped levels. Task sections start with a base-form verb ("Install the package"). Concept sections use a noun phrase ("Configuration fields").
- Use code font in prose for filenames, paths, commands, flags, code elements, and text the reader must enter. Use fenced code blocks for longer examples; add a language identifier and introduce the block with a sentence.
- Write in standard American English (behavior, center, license, color) everywhere: code, comments, docs, and commit messages.
- `README.md` is user-facing: plain sentences, second person, concrete numbers ("turn past ~15° to one side"). Keep the **Layout** section and the flag examples in step with the code.
- Research and findings go in `docs/research.md`, not the README.

### Git

- Commit subject: imperative, capitalized, no trailing period, ≤ ~72 chars (`Add nod gesture trigger (cross threshold + return quickly)`).
- Body: explain *why* and what the user notices, wrapped at ~72 columns. Use a bullet list when a change touches several areas. Mention behavior changes to defaults explicitly.
- End with the `Co-Authored-By:` trailer for the model that wrote it.
- One logical change per commit. Don't commit `config.toml`, `*.csv` logs, `.venv/`, or `*.egg-info/` (they are gitignored, so don't force-add them).
- Only commit or push when asked.

### Branches

- Feature work happens on `claude/*` branches. `master` is the main branch.
- `gui-wip` holds an older, unfinished PySide6 GUI that crashes on macOS 26. The Tkinter GUI in `gui.py` replaces it, so don't merge it or build on it.

## Definition of done

A change is finished only when all of these are true:

1. `.venv/bin/python -m pytest -q` passes, and new behavior has tests (per the trigger checklist above when relevant).
2. `.venv/bin/vn-eye --help` and `.venv/bin/vn-eye-gui --help` run without error, which shows the CLI and config still load.
3. Every new or changed config key exists in code defaults and `config.example.toml` with the same value, and works through `--set`.
4. The README matches the change when users can see it (flags, gestures, defaults, Layout).
5. Nothing violates the privacy rule. No new dependency was added without approval.
6. Your final message says what you **could not** test. Real-camera and real-key-output behavior can only be checked by a human running `vn-eye --preview` paused (press `p`), then `vn-eye` in a game. Never claim a gesture "works" from unit tests alone. Say it is unit-tested and needs a live check.
