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
  → triggers.py   Trigger.update()   → TriggerEvent (fixed event name)
  → app.py        app:* events handled here (e.g. app:toggle_pause)
  → outputs.py    ActionDispatcher   → key/mouse output (each trigger has its own cooldown)
```

The design and the planned plugin loading are in `docs/design/sources.md`.

Other modules: `config.py` (dataclasses, TOML loading, overrides), `preview.py` (debug window over the source's `debug_view()`), `pause.py` (pause switch), `feedback.py` (sounds), `app.py` (main loop and CLI).

### Rules the design depends on

1. **Triggers emit fixed event names. They never choose the output.** The only place events are mapped to outputs is `output.actions` (`OutputConfig.actions` in code, `[output.actions]` in TOML). Current event names: `blink`, `head_shake`, `head_nod_up`, `head_nod_down`, `nod_up`, `nod_down`.
2. Outputs come in two kinds. Keystroke/mouse outputs are listed in `OUTPUT_NAMES` in `outputs.py` (`enter`, `space`, `left_click`, `wheel_down`, `up`, `down`). App-level outputs start with `app:` (currently only `app:toggle_pause`). The event loop in `app.py` handles `app:` outputs before `ActionDispatcher` sees them.
3. Triggers are pure state machines. They take an `Observation` and return a `TriggerEvent` or `None`. They must not touch the camera, the face model, the OS or wall-clock time. Use `obs.timestamp` only. This is what makes them testable.
4. A trigger that loses the face (`not obs.face_present`, or a `None` head value) must `reset()` and cancel any half-done gesture.
5. Head pitch sign: **positive pitch = head tilted down** (image y grows downward). `side == 1` maps to the `*_down` event.
6. Config precedence: defaults < `--config` file < shortcut flags (`--min-duration`, `--output`, …) < `--set SECTION.KEY=VALUE`.

## Privacy (hard rule)

Camera frames are processed in memory and are **never written to disk or sent anywhere**. `--log` writes numbers only (eye and head values per frame), never images. Do not add any feature that saves frames, uploads data or adds network calls. The one exception is the existing one-time download of the face landmark model.

## Conventions

### Code

- Every module starts with a one-line docstring saying what it does, then `from __future__ import annotations`.
- Type hints on every function signature. Use `X | None` and built-in generics (`list[str]`), not `Optional`/`List`.
- Config sections are `@dataclass(frozen=True)` with defaults in code. Each non-obvious field gets a comment above it that explains the behavior in user terms (for example `# Turn past amplitude_deg to one side, then past it to the other side, within max_duration_s.`).
- Interfaces are `typing.Protocol` (`Trigger`, `Output`). Concrete classes don't inherit from them.
- Units go in names: `_s` for seconds, `_deg` for degrees (`min_duration_s`, `amplitude_deg`).
- Private state uses a leading underscore. Comments explain *why* or describe the gesture, not what the line does. Match the existing comment density, which is sparse.
- Validate config values that the type can't enforce in the constructor, and raise `ValueError` with a message that names the key and the allowed values. Example: `eyes.close_ratio must be above 0 and below eyes.open_ratio (0.75), not 0.9`.
- No new runtime dependencies without asking. Platform-specific code is imported lazily inside the class or function that needs it (see `Win32Output`, `PynputOutput`).

### User feedback and logging

- When a gesture is detected but doesn't fire, the user should be told why. Pass the optional `log` callback into the trigger and call it with a message shaped like `"{name}: <what happened> (<reason>, <limit>)"`. Example: `blink: blink 0.12s (too short, min 0.15s)`. Format durations as `.2f` seconds and angles as whole degrees with `°`.
- Use `print` through the `log` callback. Don't add the `logging` module.

### Adding a new trigger (checklist)

Do all of these in the same change:

1. Config dataclass in `config.py` (`enabled`, thresholds with `_s`/`_deg`, `cooldown_s`). There is no fixed rule yet for whether a new trigger starts on or off, so ask the user before choosing `enabled`. Add a field to `Config`.
2. Trigger class in `triggers.py` that implements `name`, `needs` (the signals it requires, for example `frozenset({HEAD_POSE})`), `update`, `reset` and `status`, then register it in `create_triggers`. A trigger whose `needs` the source doesn't provide is skipped at startup with a notice.
3. Default event → output mappings in `OutputConfig.actions`.
4. A matching section and `[output.actions]` entries in `config.example.toml`. The values there must equal the code defaults, because the file says so.
5. Tests in `tests/test_triggers.py` that drive the trigger with synthetic `Observation` streams at 30 FPS (see the `run` helper). Cover at least: it fires, it doesn't fire (each rejection reason), cooldown, and face loss.
6. The README, if users can see the change (a new gesture, flag or default).

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
- `gui-wip` holds an unfinished PySide6 GUI that crashes on macOS 26. Don't merge it or build on it unless asked to work on the GUI.

## Definition of done

A change is finished only when all of these are true:

1. `.venv/bin/python -m pytest -q` passes, and new behavior has tests (per the trigger checklist above when relevant).
2. `.venv/bin/vn-eye --help` runs without error, which shows the CLI and config still load.
3. Every new or changed config key exists in code defaults and `config.example.toml` with the same value, and works through `--set`.
4. The README matches the change when users can see it (flags, gestures, defaults, Layout).
5. Nothing violates the privacy rule. No new dependency was added without approval.
6. Your final message says what you **could not** test. Real-camera and real-key-output behavior can only be checked by a human running `vn-eye --preview --dry-run`, then `vn-eye` in a game. Never claim a gesture "works" from unit tests alone. Say it is unit-tested and needs a live check.
