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

The face landmark model (~4 MB) is downloaded on first run. The Windows executable from `build-windows.bat` includes it.

## Run the tests

```sh
pytest
```

## Build a Windows executable

You can package `eyeokuri` so it runs on a Windows PC without Python. You need Python 3.11 or later on the build PC only.

1. Double-click `build-windows.bat`. The first build takes a few minutes because it sets up `build\venv`.
2. Copy `build\eyeokuri-windows.zip` (~65 MB) to the other PC and unzip it.
3. Run `eyeokuri.exe` in the unzipped folder. It opens a console window. Close the window or press `Ctrl+C` to stop it.

The build downloads the face model and packs it into the zip, so the other PC does not need to be online. The zip also contains `LICENSE` and `THIRD_PARTY_NOTICES.md`, which carries the model's Apache 2.0 license. The About window opens both. Windows might show an "unknown publisher" warning because the executable is not signed.

## Layout

```
src/eyeokuri/
  sources/        Source interface and Signals (raw eye openness, head pose)
    opencv.py     the built-in source: webcam -> face mesh -> Signals
    face_mesh.py  MediaPipe's face model, run with OpenCV
    camera.py     webcam capture that reconnects, plus the scanner for the camera picker
  eyes.py         Signals -> Observation (open/closed vs. your open-eye level, and wink: one eye vs. the other)
  head.py         Signals -> head yaw/pitch relative to your usual pose
  triggers.py     Observation -> step boxes entered -> gestures -> TriggerEvent
  i18n.py         GUI translations: _(), N_(), language detection (no Tk; the command line stays English)
  locales/        one catalog per GUI language ({"English text": "translated text"}), e.g. ja.py, zh_tw.py
  keys.py         key names and combinations ("ctrl+s"): parsing and press order
  outputs.py      TriggerEvent -> key/mouse input
  engine.py       runs the pipeline one frame at a time (used by both front ends)
  app.py          command line: main loop and flags
  gui/            window (Tkinter); eyeokuri-gui runs gui:main
    launch.py       parses the flags and starts the main window
    main_window.py  the gesture list with on/off and pause toggles, the log, and the menu bar
    worker.py       runs the Engine on a background thread
    gesture_window.py  one gesture's window: output, plot, steps table, head limits
    about.py        About window: version, and buttons that open LICENSE and THIRD_PARTY_NOTICES.md
    config_window.py   config window: General and Advanced tabs
    wizard.py       gesture wizard for the gesture window's gesture
    plot.py         the plot with one draggable box per step
    camera.py       camera view window and the camera picker
    model.py        gesture settings as the editor's dicts, and the plot ranges (no Tk, unit-tested)
    tkutil.py       window placement and size, and fonts
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
tools/            capture_screenshots.py, which takes the site's GUI screenshots
docs/i18n/        one glossary per language (glossary.ja.tsv, glossary.zh-TW.tsv): columns en, the language code, note;
                  gui-plan.md, the rules for translating the GUI and the steps to add a language
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

The docs are set up for English, Japanese (`ja`) and Traditional Chinese for Taiwan (`zh-tw`). A docs page without a translation shows the English text with a notice.

- Use the terms in `docs/i18n/glossary.<language>.tsv`, and add a row when you settle on a new one.
- To translate a docs page, copy it to the same path under `site/src/content/docs/<language>/` and translate it.
- Screenshots show the GUI, so each language needs its own. Take them with `tools/capture_screenshots.py` (see [Take the site screenshots](#take-the-site-screenshots)), and reference `assets/screenshots/<language>/<name>.png` from the translated page.
- To translate the homepage, add the language to `site/src/i18n/home.ts`, then add `site/src/pages/<language>/index.astro` that renders `<Home locale="<language>" />`.

## Take the site screenshots

`tools/capture_screenshots.py` saves the four GUI screenshots used by the guide pages (`main-window`, `gesture-window`, `wizard-take`, `config-general`) from the real windows. It runs them on a scripted source (a blink, a head shake and steady eyes), so it needs no camera, no camera image appears, and nothing is sent to other windows. It copies pixels from the screen, so it works on Windows only.

```sh
.venv\Scripts\python tools\capture_screenshots.py --language zh-TW
```

- Leave the mouse and other windows alone while it runs (about 40 seconds).
- English screenshots go to `site/src/assets/screenshots/`; other languages go to a subfolder named after the language in lowercase (`zh-tw/`). `--out` picks another folder, and `--only main-window,wizard-take` saves only some.
- Use the same display scaling and Windows theme each time, so new screenshots match the old ones. Look at the results before you commit them.
- When the GUI changes, run it again for every language that has screenshots.

## Translate the GUI

The GUI follows the Windows display language (`app.language = "auto"`) and has Japanese (`ja`) and Traditional Chinese (`zh-TW`) catalogs. Log lines, `ValueError` messages and the command line stay English. The rules for writing translatable strings are in `docs/i18n/gui-plan.md`.

- To add a string, wrap it with `_("...")` (or `N_("...")` in a module-level constant, and `_(value)` where it shows), then add the entry to every catalog in `eyeokuri/locales/`. `tests/test_i18n.py` fails when a catalog has a missing or stale entry.
- To add a language, copy `locales/ja.py`, add it to `CATALOGS` in `i18n.py`, add the Windows locale names to `_LOCALE_LANGUAGES` (and the sentence gap and full stop to `_STYLES` if the language needs them), and add `docs/i18n/glossary.<language>.tsv`. Ask a native speaker to review the catalog before release.

## Extend eyeokuri

- To add a gesture, add a `[gestures.NAME]` section to your config. To ship it as a built-in gesture, follow the checklist in `AGENTS.md`.
- To add a signal, add it to `SIGNALS` in `config.py` and to `signal_value` in `triggers.py`.
- To add another input device, implement the `Source` protocol in `eyeokuri/sources/`. See [design/sources.md](design/sources.md).
- For how the `[eyes]` and `[head]` settings work, see [design/detection.md](design/detection.md).
