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
vn-eye --preview             # try it out: debug window (press p to pause, so gestures only print)
vn-eye                       # real use: start it, then switch to the game
vn-eye --config config.toml  # custom settings (copy config.example.toml)
vn-eye --min-duration 0.5 --blink-key left_click   # common settings as flags
vn-eye --set eyes.open_ratio=0.8                # any config key (repeatable)
```

`vn-eye --help` lists all flags. Command-line settings override the config file.

### Use the window

Run `vn-eye-gui` for a window instead of the terminal:

```sh
vn-eye-gui                       # loads config.toml if it exists
vn-eye-gui --config my.toml      # load and save another file
```

The main window shows the log: gestures that fired, gestures that didn't and why, and pauses. The status on the right shows whether vn-eye sees your face. **Camera view…** opens the live camera view with your eye outlines and signal values. vn-eye draws it only while that window is open, so close it when you don't need it to save CPU. **Pause** (or the `p` key) pauses and resumes. While paused, gestures still fire but only appear in the log (for example `blink: ... -> enter (paused, not sent)`), so you can try them without sending input.

**Gesture wizard…** sets up one gesture from your own movement, so you don't have to work out the numbers:

1. Choose a gesture and select **Start**. The first page lists the takes the wizard asks for: the gesture itself 3 times, done the way you want it to count, then each near miss once. For a blink, the near misses are a quick natural blink and a long eye closure.
2. Each take has its own page that says what to do. Select **Record** (or press Space), do it, and select **Stop**. For a too-quick or too-slow take, you also choose whether it should fire. For example, choose **Yes** on the quick blink if you want everyday blinks to advance the text. The page shows whether the take fires with the settings fitted so far. Select **Redo** to record it again, or **Next** to go on. You can skip a near miss. Gestures are off while the wizard is open, so nothing is sent to other windows.
3. The wizard fits the gesture to all your takes. It moves each step's edge to 60% of the way to your weakest take, and fits the time limits the gesture already has between your takes and the near misses. Limits that are off stay off. The review page lists whether each take fires with the new settings and what changed. Select a take to see it on the plot, and select **Redo take** to record one again.
4. Select **Use these settings**. The gesture uses the new values right away, and the wizard asks whether to save them to the config file. You can fine-tune the result in the settings window.

**Set up with wizard…** on the settings window's **Gestures** tab opens the same wizard. It starts from your unapplied edits there, and **Use these settings** puts the result back in the settings window and applies it. Select **Save** there to keep it.

Gestures whose steps are other gestures can't use the wizard. Set up the gestures they're made of instead.

**Settings…** opens the settings window. On the **Gestures** tab, each step of the selected gesture is a box on a plot of your eye and head signals. Drag a box's top or bottom edge to change its threshold, or its left or right edge to change the time allowed after the previous step. You can also type the numbers in the table below the plot.

To check your settings against your own movement, do the gesture and then select **Save last 4 s as a test**. The list shows, for every test, whether the gesture fires and, if not, why. It updates as you change the settings. Tests keep only the eye and head numbers, in memory, never images.

**Apply** uses the settings right away. **Save** also writes them to the config file. Saving rewrites the file with only the values that differ from the defaults, so comments in it are not kept.

- Keep your eyes open normally for ~2 s at start so it can learn your "eyes open" level. It keeps adapting as your posture changes.
- Blink (both eyes, at least 0.15 s): you'll hear a beep and `Enter` is sent when you reopen your eyes. Closing them for more than 2 s cancels.
- **Shake your head** to pause or resume: turn past ~15° to one side, then past ~15° to the other side, within 1 s. A different sound plays for pause and resume. Turning to look at something and back does not count. Use `--set gestures.head_shake.within_s=1.5` to allow a slower shake, or `--no-head-shake` to turn it off. A shake often comes with a blink, so shaking your head can also advance one line.
- Nodding up or down (sends the `up` or `down` arrow key) is off by default. Turn it on with `--set gestures.nod_down.enabled=true`.
- In the preview window, `p` also pauses and resumes, and `q`/`Esc` closes it. `Ctrl+C` stops `vn-eye` from the terminal.
- Every gesture that doesn't trigger is printed with the reason (too short, too long, cooldown, paused), which helps you get a feel for the timing. Set `log_rejected = false` under `[feedback]` in your config file to turn this off.
- `--log eyes.csv` writes per-frame eye values (numbers only, no images), which helps with tuning thresholds.
- The face model runs with OpenCV, and nothing is sent over the network after the one-time model download.
- If the camera stops sending frames (for example, it briefly disconnects), `vn-eye` reopens it every second until frames come back. Gestures are not detected during the gap.

## Gestures

Each gesture in your config file is a list of steps. Picture a plot of one signal over time: a step is a box on that plot, and it counts the moment the signal enters the box. The signals are:

- `eyes`: how open your eyes are, where 1.0 is your usual open level.
- `pitch`: head tilt in degrees. Positive is down.
- `yaw`: head turn in degrees. Positive is your left.

For example, the built-in blink is "eyes below 55%, then eyes above 75% between 0.15 s and 2 s later":

```toml
[gestures.blink]
steps = [
  { signal = "eyes", below_ratio = 0.55 },
  { signal = "eyes", above_ratio = 0.75, after_min_s = 0.15, after_max_s = 2.0 },
]
guards = [
  { signal = "yaw", above_deg = -20.0, below_deg = 20.0 },
  { signal = "pitch", above_deg = -15.0, below_deg = 15.0 },
]
cooldown_s = 1.0
output = "enter"
```

The `guards` keep a blink from counting while you look away. Moving your head often makes you blink, and a turned or tilted head also changes how open your eyes look. A guard is a box on `pitch` or `yaw`. While your head is outside any guard, the gesture can't start, and one in progress is canceled (the log says `blink: canceled (head yaw +25° outside its limit)`). A closure that began while your head was turned doesn't count after you turn back. By default, a blink counts only when your head is within 20° of your usual pose sideways and 15° up or down. Set `guards = []` to count blinks at any head angle. A source that doesn't report head pose ignores guards. In the settings window, the **Only while the head stays within** rows edit them.

Each step sets its own box and timing, so you can change one step without changing the others:

- `above_ratio`/`below_ratio` (eyes) or `above_deg`/`below_deg` (head) set the box. Leave one out for a box that is open on that side.
- `after_min_s`/`after_max_s` set the time allowed since the previous step. 0 means no limit.
- `hold_s` makes you stay inside the box that long before the step counts, for example to fire on looking left for 1 s.

A gesture also has `guards` (see above), `any_order` (the head shake uses it, so you can start on either side), `within_s` (time allowed from the first step to the last), `cooldown_s` and `output`.

You can add your own gesture under a new name. A step can also be another gesture, which counts when that gesture fires. This gesture sends `space` when you blink and then nod down within 1.5 s:

```toml
[gestures.nod_down]
enabled = true
output = ""           # send nothing for a nod on its own

[gestures.blink_then_nod]
steps = [{ gesture = "blink" }, { gesture = "nod_down", after_max_s = 1.5 }]
output = "space"
```

To change one step from the command line, give its position, starting from 0: `--set gestures.nod_down.steps.0.above_deg=15`.

When the same movement matches several gestures, each one fires. In this example, a blink followed by a nod also fires `blink`, so it sends `Enter` too. `config.example.toml` lists every field.

Config files must start with `version = 1`. A file without it uses an older layout, and `vn-eye` refuses to load it. Start again from `config.example.toml`.

Platform notes:
- **Windows** (main target): keys are sent with `SendInput` using hardware scan codes, so DirectInput games receive them too. If the game runs as administrator, run `vn-eye` as administrator as well, or Windows will block the input.
- **macOS**: give your terminal *Camera* permission, plus *Accessibility* (to send keys) under System Settings → Privacy & Security.

## Build a Windows executable

You can package `vn-eye` so it runs on a Windows PC without Python. You need Python 3.11 or later on the build PC only.

1. Double-click `build-windows.bat`. The first build takes a few minutes because it sets up `build\venv`.
2. Copy `build\vn-eye-windows.zip` (~65 MB) to the other PC and unzip it.
3. Run `vn-eye.exe` in the unzipped folder. It opens a console window. Close the window or press `Ctrl+C` to stop it.

The first run downloads the face model, so the PC must be online once. Windows might show an "unknown publisher" warning because the executable is not signed.

## Layout

```
src/vn_eye/
  sources/        Source interface and Signals (raw eye openness, head pose)
    opencv.py     the built-in source: webcam -> face mesh -> Signals
    face_mesh.py  MediaPipe's face model, run with OpenCV
    camera.py     webcam capture that reconnects
  eyes.py         Signals -> Observation (open/closed vs. your open-eye level)
  head.py         Signals -> head yaw/pitch relative to your usual pose
  triggers.py     Observation -> step boxes entered -> gestures -> TriggerEvent
  outputs.py      TriggerEvent -> key/mouse input
  engine.py       runs the pipeline one frame at a time (used by both front ends)
  app.py          command line: main loop and flags
  gui.py          window: log, optional camera view, settings with the gesture plot, and the gesture wizard
  tuning.py       fits a gesture's limits to takes recorded in the wizard
```

To add a gesture, add a `[gestures.NAME]` section to your config. To add a new signal, add it to `SIGNALS` in `config.py` and to `signal_value` in `triggers.py`. To add another input device, implement the `Source` protocol in `vn_eye/sources/` (see [docs/design/sources.md](docs/design/sources.md)). For how the `[eyes]` and `[head]` settings work, see [docs/design/detection.md](docs/design/detection.md).

Run the tests with `pytest`.
