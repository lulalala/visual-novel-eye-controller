# Eye tracker for playing visual novel

Visual novels (AVG) contain large amount of text. Each next line requires user inputting "enter", which can be tedius. Auto mode can solve the problem somewhat but user will have less flexiblity on controlling the pacing.

This repo aims to make an eye-tracking program which aids the reading of visual novel. Essentially we want trigger `enter` just by moving our eyeballs.

# Stage 1 - Research

Currently we'd like to gather related information. Maybe there already exists some solution (commercial/open source). If we are to develop our own, what is the difficulty level? What are the requirements (e.g. the head should still be able to move slightly during the detection)? What eye gesture is good for triggering `enter`? There are quite a few areas which needs research. If you are intersted, please head towards the wiki and add your findings.

Initial findings are collected in [docs/research.md](docs/research.md).

# Stage 2 - Prototype: long blink → Enter

`vn-eye` watches your webcam and sends `Enter` (or space, left click, or scroll-down) to the foreground window when you blink. By default any closure of both eyes lasting 0.15–2 s counts, so a natural blink advances the text. If you'd rather blink freely and close your eyes deliberately to advance, raise `--min-duration` to about 0.35–0.45 s (ordinary blinks were 0.17–0.34 s in our first test). Shake your head to pause and resume. It needs only a webcam. Frames are processed locally and never stored.

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
vn-eye --min-duration 0.5 --blink-key left_click   # common settings as flags
vn-eye --set eyes.open_ratio=0.8                # any config key (repeatable)
```

`vn-eye --help` lists all flags. Command-line settings override the config file.

- Keep your eyes open normally for ~2 s at start so it can learn your "eyes open" level. It keeps adapting as your posture changes.
- Blink (both eyes, at least 0.15 s): you'll hear a beep and `Enter` is sent when you reopen your eyes. Closing them for more than 2 s cancels.
- **Shake your head** to pause or resume: turn past ~15° to one side, then past ~15° to the other side, within 1 s. A different sound plays for pause and resume. Turning to look at something and back does not count. Use `--set gestures.head_shake.past_deg=20` to adjust, or `--no-head-shake` to turn it off. A shake often comes with a blink, so shaking your head can also advance one line.
- Nodding up or down (sends the `up` or `down` arrow key) is off by default. Turn it on with `--set gestures.nod_down.enabled=true`.
- In the preview window, `p` also pauses and resumes, and `q`/`Esc` closes it. `Ctrl+C` stops `vn-eye` from the terminal.
- Every gesture that doesn't trigger is printed with the reason (too short, too long, cooldown, paused), which helps you get a feel for the timing. Set `log_rejected = false` under `[feedback]` in your config file to turn this off.
- `--log eyes.csv` writes per-frame eye values (numbers only, no images), which helps with tuning thresholds.
- The face model runs with OpenCV, and nothing is sent over the network after the one-time model download.
- If the camera stops sending frames (for example, it briefly disconnects), `vn-eye` reopens it every second until frames come back. Gestures are not detected during the gap.

## Gestures

Each gesture in your config file is a list of states to reach in order: `eyes_closed`, `eyes_open`, `head_down`, `head_up`, `head_left`, `head_right` or `head_center`. A step counts the moment you reach that state. For example, the built-in blink and head shake are:

```toml
[gestures.blink]
steps = ["eyes_closed", "eyes_open"]
gap_min_s = 0.15      # time between two steps in a row: here, how long
gap_max_s = 2.0       # your eyes stay closed
output = "enter"

[gestures.head_shake]
steps = ["head_left", "head_right"]
any_order = true      # right, then left also counts
past_deg = 15.0       # the head counts as turned past 15°...
release_deg = 10.0    # ...and as back at center within 10°
within_s = 1.0        # time from the first step to the last
cooldown_s = 1.5
output = "app:toggle_pause"
```

Steps that a gesture doesn't list are skipped. In the head shake, your head passes `head_center` between the two sides, which is fine. `head_center` only counts on the axis the gesture turns or tilts on, so in a nod (`["head_down", "head_center"]`), turning your head back from the side doesn't count as the return.

You can add your own gesture under a new name. A step can also be another gesture's name. This gesture sends `space` when you blink and then nod down within 1.5 s:

```toml
[gestures.nod_down]
enabled = true
output = ""           # send nothing for a nod on its own

[gestures.blink_then_nod]
steps = ["blink", "nod_down"]
within_s = 1.5
output = "space"
```

When the same movement matches several gestures, each one fires. In this example, a blink followed by a nod also fires `blink`, so it sends `Enter` too. `config.example.toml` lists every field.

Config files must start with `version = 1`. A file without it uses an older layout, and `vn-eye` refuses to load it. Start again from `config.example.toml`.

Platform notes:
- **Windows** (main target): keys are sent with `SendInput` using hardware scan codes, so DirectInput games receive them too. If the game runs as administrator, run `vn-eye` as administrator as well, or Windows will block the input.
- **macOS**: give your terminal *Camera* permission, plus *Accessibility* (to send keys) under System Settings → Privacy & Security.

## Layout

```
src/vn_eye/
  sources/        Source interface and Signals (raw eye openness, head pose)
    opencv.py     the built-in source: webcam -> face mesh -> Signals
    face_mesh.py  MediaPipe's face model, run with OpenCV
    camera.py     webcam capture that reconnects
  eyes.py         Signals -> Observation (open/closed vs. your open-eye level)
  head.py         Signals -> head yaw/pitch relative to your usual pose
  triggers.py     Observation -> states reached -> gestures -> TriggerEvent
  outputs.py      TriggerEvent -> key/mouse input
  app.py          main loop and CLI
```

To add a gesture made of existing states, add a `[gestures.NAME]` section to your config. To add a new state, add it to `STATES` in `config.py` and to `StateTracker` in `triggers.py`. To add another input device, implement the `Source` protocol in `vn_eye/sources/` (see [docs/design/sources.md](docs/design/sources.md)). For how the `[eyes]` and `[head]` settings work, see [docs/design/detection.md](docs/design/detection.md).

Run the tests with `pytest`.
