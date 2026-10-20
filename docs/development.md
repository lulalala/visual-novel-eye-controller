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
  keys.py         key names and combinations ("ctrl+s"): parsing and press order
  outputs.py      TriggerEvent -> key/mouse input
  engine.py       runs the pipeline one frame at a time (used by both front ends)
  app.py          command line: main loop and flags
  gui/            window (Tkinter); eyeokuri-gui runs gui:main
    launch.py       parses the flags and starts the main window
    main_window.py  the log, and the buttons for pause, camera view, settings and the wizard
    worker.py       runs the Engine on a background thread
    settings.py     settings window: gesture list, plot, steps table, General and Advanced tabs
    wizard.py       gesture wizard
    plot.py         the plot with one draggable box per step
    camera.py       camera view window and the camera picker
    model.py        gesture settings as the editor's dicts, and the plot ranges (no Tk, unit-tested)
    tkutil.py       window placement and fonts
  theme.py        the window's colors and ttk styles, taken from the site's palette
  icons/          the logo as PNG window icons (Tk 8.6 can't read SVG)
  tuning.py       fits a gesture's limits to takes recorded in the wizard
site/             static site (Astro with Starlight)
  astro.config.mjs  site settings, languages and docs sidebar
  src/pages/      homepage routes: index.astro (English), one folder per added language
  src/components/ Home.astro, the homepage
  src/i18n/       home.ts, the homepage text for each language
  src/scripts/    home.js, the homepage demo
  src/styles/     home.css (homepage) and docs.css (docs theme)
  src/content/docs/  docs pages in Markdown; translations go in ja/ and zh-tw/
```

## Update the window icons

The GUI's window icons in `src/eyeokuri/icons/` are PNG copies of `logo/eye-static.svg`. When you change the logo, regenerate them with a Python whose Tk is 9.0 or later (`python -c "import tkinter; print(tkinter.TkVersion)"`), since Tk 9 can read SVG:

```sh
python -c "
import tkinter as tk
tk.Tk().withdraw()
for n in (16, 32, 48, 64, 128):
    tk.PhotoImage(file='logo/eye-static.svg', format=f'svg -scale {n / 352}').write(f'src/eyeokuri/icons/eyeokuri-{n}.png', format='png')
"
```

## Build the site

The site needs Node.js 22.22 or later. In `site/`, run `npm install` once, then:

- `npm run dev` serves the site at `http://localhost:4321/` and reloads on each edit.
- `npm run build` writes the site to `site/dist/`, which you can host on any static file server.
- `npm run preview` serves the built `site/dist/`.

`site/dist/`, `site/node_modules/` and `site/.astro/` are gitignored. The homepage loads two fonts from Google Fonts; nothing else leaves the page. Astro collects anonymous usage data by default; run `npx astro telemetry disable` to opt out.

## Translate the site

The docs are set up for English, Japanese (`ja`) and Traditional Chinese (`zh-tw`). A docs page without a translation shows the English text with a notice.

- To translate a docs page, copy it to the same path under `site/src/content/docs/ja/` or `zh-tw/` and translate it.
- To translate the homepage, add the language to `site/src/i18n/home.ts`, then add `site/src/pages/<language>/index.astro` that renders `<Home locale="<language>" />`.

## Extend eyeokuri

- To add a gesture, add a `[gestures.NAME]` section to your config. To ship it as a built-in gesture, follow the checklist in `AGENTS.md`.
- To add a signal, add it to `SIGNALS` in `config.py` and to `signal_value` in `triggers.py`.
- To add another input device, implement the `Source` protocol in `eyeokuri/sources/`. See [design/sources.md](design/sources.md).
- For how the `[eyes]` and `[head]` settings work, see [design/detection.md](design/detection.md).
