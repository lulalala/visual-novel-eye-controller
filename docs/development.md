# Development

This page is for people who change or build `eyeokuri`. For using the app, see the [README](../README.md).

## Project stages

- Stage 1 (research) is done. Findings are in [research.md](research.md).
- Stage 2 (current) is a working webcam prototype. A blink sends `Enter`, and a head shake pauses and resumes.

## Set up a development environment

Requires Python 3.11+.

```sh
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

The face landmark model (~4 MB) is downloaded on first run.

## Run the tests

```sh
pytest
```

## Build a Windows executable

You can package `eyeokuri` so it runs on a Windows PC without Python. You need Python 3.11 or later on the build PC only.

1. Double-click `build-windows.bat`. The first build takes a few minutes because it sets up `build\venv`.
2. Copy `build\eyeokuri-windows.zip` (~65 MB) to the other PC and unzip it.
3. Run `eyeokuri.exe` in the unzipped folder. It opens a console window. Close the window or press `Ctrl+C` to stop it.

The first run downloads the face model, so the PC must be online once. Windows might show an "unknown publisher" warning because the executable is not signed.

## Layout

```
src/eyeokuri/
  sources/        Source interface and Signals (raw eye openness, head pose)
    opencv.py     the built-in source: webcam -> face mesh -> Signals
    face_mesh.py  MediaPipe's face model, run with OpenCV
    camera.py     webcam capture that reconnects, plus the scanner for the camera picker
  eyes.py         Signals -> Observation (open/closed vs. your open-eye level)
  head.py         Signals -> head yaw/pitch relative to your usual pose
  triggers.py     Observation -> step boxes entered -> gestures -> TriggerEvent
  outputs.py      TriggerEvent -> key/mouse input
  engine.py       runs the pipeline one frame at a time (used by both front ends)
  app.py          command line: main loop and flags
  gui.py          window: log, optional camera view, settings with the gesture plot, and the gesture wizard
  tuning.py       fits a gesture's limits to takes recorded in the wizard
site/             static homepage
  src/            index.html, style.css and main.js, with markers that build.py fills in
  build.py        writes site/dist/ (the page with its CSS, JS and logo inlined)
```

## Build the homepage

Run `python site/build.py`. It writes `site/dist/index.html` and `site/dist/logo.svg`, which you can host on any static file server. The build uses only the standard library. `site/dist/` is gitignored. The page loads two fonts from Google Fonts; nothing else leaves the page.

## Extend eyeokuri

- To add a gesture, add a `[gestures.NAME]` section to your config. To ship it as a built-in gesture, follow the checklist in `AGENTS.md`.
- To add a signal, add it to `SIGNALS` in `config.py` and to `signal_value` in `triggers.py`.
- To add another input device, implement the `Source` protocol in `eyeokuri/sources/`. See [design/sources.md](design/sources.md).
- For how the `[eyes]` and `[head]` settings work, see [design/detection.md](design/detection.md).
