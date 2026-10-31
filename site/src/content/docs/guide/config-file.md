---
title: Edit gestures in the config file
sidebar:
  order: 6
description: Write gestures as steps in config.toml, choose what they send, and combine them.
---

The gesture window edits the same settings that `config.toml` holds. Edit the file directly when you want to copy a gesture, add many gestures or use [command-line options](https://github.com/lulalala/eyeokuri/blob/master/docs/command-line.md). The installed app keeps the file at `%APPDATA%\eyeokuri\config.toml`. [`config.example.toml`](https://github.com/lulalala/eyeokuri/blob/master/config.example.toml) lists every field.

Config files must start with `version = 1`. A file without it uses an older layout, and eyeokuri refuses to load it. Start again from `config.example.toml`.

## Write a gesture

Each gesture is a list of steps. A step is a box on a plot of one signal over time, and it counts the moment the signal enters the box. See [Read the plot](../edit-a-gesture/#read-the-plot) for the signals: `eyes`, `wink`, `pitch`, `yaw` and `roll`.

The built-in blink is "eyes below 60%, then eyes above 70% between 0.1 s and 1 s later":

```toml
[gestures.blink]
steps = [
  { signal = "eyes", below_ratio = 0.6 },
  { signal = "eyes", above_ratio = 0.7, after_min_s = 0.1, after_max_s = 1.0 },
]
guards = [
  { signal = "yaw", above_deg = -20.0, below_deg = 20.0 },
  { signal = "pitch", above_deg = -10.0, below_deg = 10.0 },
]
cooldown_s = 1.0
output = "enter"
```

Each step sets its own box and timing, so you can change one step without changing the others:

| Field | Meaning |
| --- | --- |
| `above_ratio`, `below_ratio` | The box for `eyes` and `wink`. Leave one out for a box that is open on that side. |
| `above_deg`, `below_deg` | The box for `pitch`, `yaw` and `roll`. |
| `after_min_s`, `after_max_s` | The time allowed since the previous step. 0 means no limit. |
| `hold_s` | How long the signal must stay in the box before the step counts, for example to fire on looking left for 1 s. |

A gesture also has these fields:

| Field | Meaning |
| --- | --- |
| `guards` | Boxes on `pitch` or `yaw` that the head must stay inside. |
| `any_order` | Lets the steps happen in either order. The head shake uses it. |
| `within_s` | The time allowed from the first step to the last. |
| `cooldown_s` | The time after the gesture fires during which it can't fire again. |
| `enabled` | Turns the gesture on or off. |
| `output` | What the gesture sends. |
| `output_mode` | `press` (the default) sends the output once; `while` holds it down until the gesture ends. |

The same names appear as the columns and rows of the [gesture window](../edit-a-gesture/#change-a-limit).

## Keep a gesture from firing while you look away

A guard is a box on `pitch` or `yaw`. While your head is outside any guard, the gesture can't start, and one in progress is canceled. The log says why, for example `blink: canceled (head yaw +25° outside its limit)`. A closure that began while your head was turned doesn't count after you turn back.

By default, a blink counts only when your head is within 20° of your usual pose sideways and 10° up or down. 10° stays inside the nods' 12°, so the eye movement during a nod doesn't also count as a blink. Set `guards = []` to count blinks at any head angle. In the gesture window, the **Only while the head stays within** rows edit the guards.

## Choose what the gesture sends

`output` is one of these:

- A key: `a`–`z`, `0`–`9`, `f1`–`f24`, `enter`, `space`, `tab`, `escape`, `backspace`, `delete`, `insert`, `home`, `end`, `page_up`, `page_down`, `up`, `down`, `left` or `right`.
- A key after one or more modifiers (`ctrl`, `shift`, `alt`, `win`), joined with `+`, for example `ctrl+s` or `shift+tab`.
- A mouse input: `mouse_left_click`, `mouse_right_click` or `mouse_wheel_down`.
- `app_pause_toggle`, which pauses or resumes eyeokuri.
- `""`, which sends nothing.

`output_mode` sets how the output is sent: `press` (the default) sends it once, and `while` holds it down until the gesture ends. [Hold a key down](../main-window/#hold-a-key-down) explains each one and when eyeokuri lets go. This gesture holds `ctrl`, which skips text in many games, while you keep your left eye closed:

```toml
[gestures.skip]
steps = [{ signal = "wink", above_ratio = 0.25, hold_s = 0.3 }]
output = "ctrl"
output_mode = "while"   # let go when you open your left eye
```

## Combine gestures

You can add your own gesture under a new name. A step can also be another gesture, which counts when that gesture fires. This gesture sends `space` when you blink and then nod down within 1.5 s:

```toml
[gestures.nod_down]
enabled = true
output = ""           # send nothing for a nod on its own

[gestures.blink_then_nod]
steps = [{ gesture = "blink" }, { gesture = "nod_down", after_max_s = 1.5 }]
output = "space"
```

When the same movement matches several gestures, each one fires. In this example, a blink followed by a nod also fires `blink`, so it sends `Enter` too.

## Give a program its own config

The second tab of the [main window](../main-window/#use-different-keys-for-each-program) saves each program's config in a `configs` folder next to `config.toml`. The installed app uses `%APPDATA%\eyeokuri\configs\`. The file holds the program's executable name, the tab name and the gesture fields that differ from `config.toml`:

```toml
version = 1

[program]
exe = "CLANNAD.exe"   # matched with any capitalization
name = "CLANNAD"      # shown on the tab

[gestures.blink]
output = "space"
```

- A program's config can hold only `[program]` and `[gestures.NAME]` sections. Camera, eye, head, feedback and app settings come from `config.toml`.
- A field the file leaves out comes from `config.toml`, so a later change there reaches the program too.
- A gesture that isn't in `config.toml` needs its `steps`.
- eyeokuri reads these files when it starts. It skips a file it can't use and says why in the log.
- To stop using a program's config, delete its file and restart eyeokuri.
