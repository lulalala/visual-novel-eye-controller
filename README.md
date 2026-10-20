# eyeokuri

Read your visual novel hands-free. `eyeokuri` watches your webcam and advances the text when you blink, so you can keep your hands off the keyboard and mouse.

- **Blink to advance.** A blink sends `Enter` to the game. You can send any other key, a key combination such as `Ctrl+S`, a left click or a scroll-down instead.
- **Shake your head to pause.** Shake again to resume, for example when you look away or answer the phone.
- **Make it fit you.** A gesture wizard learns your blink from a few practice takes. You can also edit each gesture's thresholds and timing in the settings window.
- **Private.** It needs only a webcam. Frames are processed on your PC and never stored or sent anywhere.

By default any closure of both eyes lasting 0.15–2 s counts, so a natural blink advances the text. If you'd rather blink freely and close your eyes deliberately to advance, raise the blink's minimum closed time to about 0.35–0.45 s in the settings window (or run the wizard with a deliberate blink) (ordinary blinks were 0.17–0.34 s in our first test).

## Install

Requires Python 3.11+.

```sh
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

The face landmark model (~4 MB) is downloaded on first run. To build a standalone Windows executable or work on the code, see [docs/development.md](docs/development.md).

## Run

```sh
eyeokuri-gui                       # loads config.toml if it exists
eyeokuri-gui --config my.toml      # load and save another file
```

Keep your eyes open normally for ~2 s at start so it can learn your "eyes open" level. It keeps adapting as your posture changes. Then switch to your game.

To run without a window, see [docs/command-line.md](docs/command-line.md).

## Use the window

The main window shows the log: gestures that fired, gestures that didn't and why (too short, too long, cooldown, paused), and pauses. The status on the right shows whether eyeokuri sees your face. **Camera view…** opens the live camera view with your eye outlines and signal values. eyeokuri draws it only while that window is open, so close it when you don't need it to save CPU. In the settings window, **General** has a **Choose from live views…** button next to `camera.index`. It lists every camera it finds with its live view, and you click the one to use.

**Pause** (or the `p` key) pauses and resumes. While paused, gestures still fire but only appear in the log (for example `blink: ... -> enter (paused, not sent)`), so you can try them without sending input.

## Default gestures

- **Blink** (both eyes closed at least 0.15 s): you hear a beep and `Enter` is sent when you reopen your eyes. Closing them for more than 2 s cancels.
- **Shake your head** to pause or resume: turn past ~15° to one side, then past ~15° to the other side, within 1 s. A different sound plays for pause and resume. Turning to look at something and back does not count. A shake often comes with a blink, so it can also advance one line.
- **Nod up or down** (sends the `up` or `down` arrow key) is off by default. Turn it on in the settings window.

## Set up a gesture with the wizard

**Gesture wizard…** sets up one gesture from your own movement, so you don't have to work out the numbers:

1. Choose a gesture and select **Start**. The wizard asks for the gesture itself 3 times, done the way you want it to count, then each near miss once. For a blink, the near misses are a quick natural blink and a long eye closure.
2. Each take has its own page that says what to do. Select **Record** (or press Space), do it, and select **Stop**. For a too-quick or too-slow take, you also choose whether it should fire. For example, choose **Yes** on the quick blink if you want everyday blinks to advance the text. The page shows whether the take fires with the settings fitted so far. Select **Redo** to record it again, or **Next** to go on. You can skip a near miss. Gestures are off while the wizard is open, so nothing is sent to other windows.
3. The wizard fits the gesture to all your takes. It moves each step's edge to 60% of the way to your weakest take, and fits the time limits the gesture already has between your takes and the near misses. Limits that are off stay off. The review page lists whether each take fires with the new settings and what changed. Select a take to see it on the plot, and select **Redo take** to record one again.
4. Select **Use these settings**. The gesture uses the new values right away, and the wizard asks whether to save them to the config file. You can fine-tune the result in the settings window.

**Set up with wizard…** on the settings window's **Gestures** tab opens the same wizard. It starts from your edits there, and **Use these settings** puts the result back in the settings window. Select **OK** there to keep it.

Gestures whose steps are other gestures can't use the wizard. Set up the gestures they're made of instead.

## Edit settings

**Settings…** opens the settings window. On the **Gestures** tab, each step of the selected gesture is a box on a plot of your eye and head signals. Drag a box's top or bottom edge to change its threshold, or its left or right edge to change the time allowed after the previous step. You can also type the numbers in the table below the plot.

To check your settings against your own movement, do the gesture and then select **Save last 4 s as a test**. The list shows, for every test, whether the gesture fires and, if not, why. It updates as you change the settings. Tests keep only the eye and head numbers, in memory, never images.

eyeokuri uses your changes as soon as you make them, but gestures stay off and the main window's buttons are disabled while the settings window is open. **OK** saves the settings to the config file and closes the window. **Cancel** goes back to the settings you had when you opened the window and closes it. Closing the window any other way works like **Cancel**, but asks first if you changed something. Saving rewrites the file with only the values that differ from the defaults, so comments in it are not kept.

If the camera stops sending frames (for example, it briefly disconnects), eyeokuri reopens it every second until frames come back. Gestures are not detected during the gap. Set `log_rejected = false` under `[feedback]` in your config file to stop logging gestures that don't fire.

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

`output` is what the gesture sends:

- A key: `a`–`z`, `0`–`9`, `f1`–`f24`, `enter`, `space`, `tab`, `escape`, `backspace`, `delete`, `insert`, `home`, `end`, `page_up`, `page_down`, `up`, `down`, `left` or `right`.
- A key after one or more modifiers (`ctrl`, `shift`, `alt`, `win`), joined with `+`, for example `ctrl+s` or `shift+tab`. On macOS, `win` is the Command key.
- A mouse input: `left_click`, `right_click` or `wheel_down`.
- `app:toggle_pause`, which pauses or resumes eyeokuri, or `""` to send nothing.

In the settings window you can type the output, or select **Press a key…** and press the key or combination.

You can add your own gesture under a new name. A step can also be another gesture, which counts when that gesture fires. This gesture sends `space` when you blink and then nod down within 1.5 s:

```toml
[gestures.nod_down]
enabled = true
output = ""           # send nothing for a nod on its own

[gestures.blink_then_nod]
steps = [{ gesture = "blink" }, { gesture = "nod_down", after_max_s = 1.5 }]
output = "space"
```

To change one step from the command line, see [docs/command-line.md](docs/command-line.md).

When the same movement matches several gestures, each one fires. In this example, a blink followed by a nod also fires `blink`, so it sends `Enter` too. `config.example.toml` lists every field.

Config files must start with `version = 1`. A file without it uses an older layout, and `eyeokuri` refuses to load it. Start again from `config.example.toml`.

## Windows notes

Keys are sent with `SendInput` using hardware scan codes, so DirectInput games receive them too. If the game runs as administrator, run `eyeokuri` as administrator as well, or Windows will block the input.
