# Eye tracker for playing visual novel

Visual novels (AVG) contain large amount of text. Each next line requires user inputting "enter", which can be tedius. Auto mode can solve the problem somewhat but user will have less flexiblity on controlling the pacing.

This repo aims to make an eye-tracking program which aids the reading of visual novel. Essentially we want trigger `enter` just by moving our eyeballs.

# Stage 1 - Research

Currently we'd like to gather related information. Maybe there already exists some solution (commercial/open source). If we are to develop our own, what is the difficulty level? What are the requirements (e.g. the head should still be able to move slightly during the detection)? What eye gesture is good for triggering `enter`? There are quite a few areas which needs research. If you are intersted, please head towards the wiki and add your findings.

Initial findings are collected in [docs/research.md](docs/research.md).

# Stage 2 - Prototype: long blink → Enter

`vn-eye` watches your webcam and sends `Enter` (or space, left click, or scroll-down) to the foreground window when you close both eyes deliberately. By default that means 0.35–2 s, while normal blinks are usually shorter (0.17–0.34 s in our first test). It needs only a webcam. Frames are processed locally and never stored.

## Setup

Requires Python 3.11+.

```sh
python -m venv .venv
# macOS/Linux: source .venv/bin/activate    Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

The face landmark model (~4 MB) is downloaded on first run.

## Run

```sh
vn-eye --preview --dry-run   # try it out: debug window, prints instead of pressing keys
vn-eye                       # real use: start it, then switch to the game
vn-eye --config config.toml  # custom settings (copy config.example.toml)
```

- Keep your eyes open normally for ~2 s at start so it can learn your "eyes open" level. It keeps adapting as your posture changes.
- Close both eyes for about 0.35 s or longer, then open them: you'll hear a beep and `Enter` is sent. Closing them for more than 2 s cancels.
- `Ctrl+Alt+P` pauses and resumes (also `p` in the preview window). `q`/`Esc` closes the preview; `Ctrl+C` stops it from the terminal.
- `--log eyes.csv` writes per-frame eye values (numbers only, no images), which helps with tuning thresholds.

Platform notes:
- **Windows** (main target): keys are sent with `SendInput` using hardware scan codes, so DirectInput games receive them too. If the game runs as administrator, run `vn-eye` as administrator as well, or Windows will block the input.
- **macOS**: give your terminal *Camera* permission, plus *Accessibility* (to send keys) and *Input Monitoring* (for the pause hotkey) under System Settings → Privacy & Security.

## Layout

```
src/vn_eye/
  landmarks.py  camera frame -> FaceFrame (MediaPipe backend; other backends plug in here)
  eyes.py       FaceFrame -> EyeObservation (eye openness, adaptive open/closed state)
  triggers.py   EyeObservation -> TriggerEvent (LongBlinkTrigger; add gaze triggers here)
  outputs.py    TriggerEvent -> key/mouse input, with cooldown
  app.py        main loop and CLI
```

To add a gesture (e.g. dwell on a zone), implement the `Trigger` protocol and register it in `create_triggers`. For a gaze source, add a backend in `landmarks.py` and a gaze field to `EyeObservation`.

Run the tests with `pytest`.
