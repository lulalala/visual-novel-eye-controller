# Command line

`eyeokuri` runs in a terminal without a window. It uses the same settings and gestures as `eyeokuri-gui`. For the window, see the [README](../README.md).

## Run from the terminal

```sh
eyeokuri --preview             # try it out: debug window (press p to pause, so gestures only print)
eyeokuri                       # real use: start it, then switch to the game
eyeokuri --config config.toml  # custom settings (copy config.example.toml)
eyeokuri --min-duration 0.5 --blink-key ctrl+enter   # common settings as flags
eyeokuri --set eyes.open_ratio=0.8                # any config key (repeatable)
```

`eyeokuri --help` lists all flags. Command-line settings override the config file.

## Set a config value

`--set SECTION.KEY=VALUE` changes any config key and can be repeated. To change one step of a gesture, give its position, starting from 0:

```sh
eyeokuri --set gestures.nod_down.steps.0.above_deg=15
eyeokuri --set gestures.head_shake.within_s=1.5     # allow a slower shake
eyeokuri --set gestures.nod_down.enabled=true       # turn on nodding
eyeokuri --set gestures.blink.output=page_down    # any key, or a combination like ctrl+s
```

Common settings also have flags, such as `--min-duration`, `--blink-key` and `--no-head-shake` (turns the head shake off).

If the config file has `paused = true` under `[app]` (the GUI saves it when you pause), `eyeokuri` starts paused. The command line never writes it. To start running anyway, use `--set app.paused=false`.

## Preview window

`--preview` opens a window with your eye outlines and signal values.

- `p` pauses and resumes. While paused, gestures still fire but only appear in the log.
- `q` or `Esc` closes the window.
- `Ctrl+C` stops `eyeokuri` from the terminal.

## Log values to a file

`--log eyes.csv` writes per-frame eye and head values (numbers only, no images). It helps with tuning thresholds.
