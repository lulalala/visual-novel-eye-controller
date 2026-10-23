# GUI translation plan

This plan covers translating the `eyeokuri-gui` windows into other languages, starting with Traditional Chinese (Taiwan), `zh-TW`. Work through the phases in order; each phase is one commit. Read `AGENTS.md` first: its rules (no new runtime dependencies, tests without Tk or a camera, column-aligned layout) apply to every phase.

## Status

| Phase | State |
|---|---|
| 0. Reword sentences so values sit outside them | Done in `f676b45` |
| 1. Translation core and language choice | Done, with the `app.language` key |
| 2. Wrap the GUI strings | Done: 181 strings; the zh-TW catalog is still empty |
| 3. zh-TW catalog | Done, awaiting native review |
| 4. Layout pass | Code done; waiting for the user's visual check |
| 5. Docs | Done |

Update this table when you finish a phase.

## Scope

The GUI has about 230 user-facing strings and 1,200 words, in `src/eyeokuri/gui/*.py` and `src/eyeokuri/tuning.py` (wizard prompts and fit notes).

Translate:

- Window titles, menus, buttons, labels, checkboxes, column headings and help text.
- `messagebox` titles and text.
- The status bar states in `gui/worker.py` (`Paused`, `No face`, `Watching`, ...).
- Plot text in `gui/plot.py` and the lane hints in `SIGNAL_PLOTS` (`gui/model.py`).
- Wizard prompts, `KIND_LABELS` and the fit notes in `tuning.py`.
- The help next to each setting (`_GENERAL_HELP`) and the section headings in `gui/config_window.py`.

Keep in English. The user decided this; don't translate these without asking:

- Trigger reasons and every log line, including the GUI's own `worker.log()` lines. They are shared with the CLI and `--log`, and tests match their text. The gesture window and wizard show a trigger reason after a translated label (`✕ Doesn't fire: <reason>`); that mix is expected.
- `ValueError` messages from `config.py`, `triggers.py` and `keys.py`, which the config and gesture windows show as errors.
- Identifiers: gesture names (`blink`, `nod_down`, user-defined names), config keys on the Advanced tab (`baseline_window_s`), signal names in comboboxes (`eyes`, `pitch`, `yaw`), key names (`Enter`, `ctrl+s`) and units (`s`, `°`).
- `config.example.toml` and the comments written by `dump_config()`.

## Rules for every translatable string

Phase 0 already rewrote the sentences to follow these rules. Keep new strings to them too.

1. **Only literals go into the catalog.** `_()` takes a plain string literal, never an f-string or a variable. Put the changeable part outside: `_("Recorded:") + f" {t:.1f} s"`.
2. **Values go after the sentence, not inside it.** Use a label ending in a colon (`Now: 0.62`), or a sentence followed by the value on its own line (`Delete this gesture?\n\nblink`). Don't add `{name}` placeholders.
3. **A noun followed by a number is fine**: `Step 2`, `Take 2 / 5`, `Camera 1`. Translate the noun (`_("Step")`) and append the number.
4. **Each branch of a conditional is its own complete string.** Write `_("Couldn't turn on this gesture:") if enabled else _("Couldn't turn off this gesture:")`, never `"turn " + ("on" if enabled else "off")`.
5. **Punctuation belongs to the translated string.** Include the colon in `_("Now:")`, so zh-TW can use a full-width `：`. Don't capitalize, lowercase or add a period to a translated string in code (`.capitalize()`, `[:1].upper()`); store it the way it's shown.
6. **No plural forms.** Write counts as a label: `Too-slow takes that still fire: 2.`
7. **Mark strings in module-level constants with `N_()`** (returns its argument unchanged) and call `_(value)` where you display them. This covers `KIND_LABELS`, `SIGNAL_PLOTS` hints, `_GENERAL_HELP`, `suggestions()` and section headings. Constants are built at import time, before the language is set, so `_()` in a constant would always return English.

## Phase 1: translation core and language choice

Add `src/eyeokuri/i18n.py`. It has no Tk imports, because `tuning.py` uses it too.

- `_(text)` returns the active catalog's translation, or `text` when the entry is missing or the language is English. `N_(text)` returns `text`.
- `set_language(code)` picks the catalog. Call it once in `gui/launch.py` before any window is built. The language changes only when the GUI restarts.
- Catalogs are plain Python dicts, `{"English text": "translated text"}`, one module per language: `src/eyeokuri/locales/zh_tw.py`. Import them statically from `i18n.py` (a `CATALOGS` dict), so PyInstaller bundles them without `hiddenimports` or `--add-data`. Don't use stdlib `gettext`: it needs compiled `.mo` files and adds a build step.
- Detect the language from the Windows UI language. Call `ctypes.windll.kernel32.GetUserDefaultUILanguage()` lazily inside a function, and map the LANGID with `locale.windows_locale` (`0x0404` → `zh_TW`). Fall back to English on other platforms or unknown languages. Match the region: `zh_TW` and `zh_HK` get `zh-TW`; `zh_CN` gets English until there's a `zh-CN` catalog.
- The CLI never calls `set_language()`, so it stays English.

The user chose to add a config key that overrides detection (done): `app.language = "auto"` (`"auto"`, `"en"` or a catalog code). It needs the usual steps: the default in `AppConfig`, the same value in `config.example.toml`, validation in the constructor with a `ValueError` listing allowed values, and a check that `--set app.language=en` works. Adding the key doesn't change what old files mean, so don't bump `CONFIG_VERSION`.

Add `tests/test_i18n.py`:

- `_()` falls back to the English text when an entry is missing, and when no language is set.
- Language detection maps `zh_TW`, `zh_HK`, `zh_CN`, `ja_JP` and an unknown code correctly. Test the mapping function with a code string; don't call Windows APIs in tests.
- A catalog check that parses every `.py` file under `src/eyeokuri` with `ast`. It collects the arguments of `_()` and `N_()` calls, and fails when:
  - an argument isn't a string literal (an f-string or a variable passed to `N_()`);
  - a catalog is missing an entry, or has an entry that is no longer in the source.

  `_()` calls with a variable argument are allowed only for values marked with `N_()`. The check skips them.

## Phase 2: wrap the GUI strings

Wrap every string in scope with `_()` or `N_()`, following the rules above. With an empty catalog the GUI must look exactly as before, and `pytest` must pass unchanged.

Strings per file (approximate):

| File | Strings | Notes |
|---|---|---|
| `gui/wizard.py` | 47 | `_outcome()` returns translated text |
| `tuning.py` | 48 | Fit notes: wrap each sentence and label separately, e.g. `_("Step") + f" {i + 1} · {signal}: " + _("Edge moved.") + " " + _("Now:") + ...` |
| `gui/gesture_window.py` | 46 | |
| `gui/config_window.py` | 26 | Section headings: replace `section.capitalize()` with a `N_()` map |
| `gui/main_window.py` | 23 | |
| `gui/plot.py` | 10 | |
| `gui/camera.py` | 9 | |
| `gui/worker.py` | 7 | Status states only; leave `self.log(...)` lines |
| `gui/about.py`, `gui/model.py`, `gui/launch.py`, `gui/tkutil.py` | 15 | |

Leave alone: Tk style names (`Wizard.TButton`), font names, combobox values, and `result.reason` (rule exception: the reason is English, so `gesture_window.py` may keep capitalizing its first letter).

One Tk dialog doesn't follow the catalog:

- `messagebox` dialogs on Windows are native, so Windows translates their **Yes**, **No** and **OK** buttons.

The **New gesture…** name prompt used `simpledialog.askstring`, whose **OK** and **Cancel** are English. The user chose to replace it, so `gui/name_dialog.py` (`ask_text`) is a small `Toplevel` dialog that uses the catalog.

## Phase 3: zh-TW catalog

Fill `src/eyeokuri/locales/zh_tw.py` with every entry the Phase 1 check lists.

- Use the terms in `docs/i18n/glossary.zh-TW.tsv` (gesture = 動作, step = 步驟, wizard = 精靈, webcam = 視訊鏡頭, frame = 畫面). Add a row for each new GUI term you settle on, such as take, edge, fire, near miss, baseline, cooldown and head limit.
- Match the tone of the zh-TW homepage in `site/src/i18n/home.ts`: plain and friendly, addressed with 你.
- Keep identifiers, units and key names in Latin, as the glossary says.
- Use full-width punctuation (`：`, `，`, `。`, `？`) inside translated strings.
- Strings joined by `" "` in code leave a space between Chinese sentences. Leave that for now and note any place where it looks wrong for phase 4.

A native speaker must review the catalog before release. Say so in the commit body.

## Phase 4: layout pass

Translated text changes widths, and the GUI rules require column-aligned layout. Check these places, where a fixed size might clip or misalign text:

- `wraplength` values: 640 (config and gesture windows), 380 (config help), `_WIZARD_WRAP = 760` (wizard).
- Fixed widths: wizard review columns 170 and 340 (`wizard.py`), the **Record** button `width=12`, comboboxes `width=18`, `✕` buttons `width=3`.
- The plot's `Fires:` label, which flips sides at `width - 90` (`plot.py`).
- Main window column headings and the status bar.

Agents can't see the windows. Make the code changes this list needs (for example, a width from text measurement instead of a constant), then list every window for the user to check by eye with `zh-TW` active: main window, config window (both tabs), gesture window, camera picker, wizard take page and review page, About. Fonts: Tk on Windows falls back to a CJK font for Segoe UI by itself; report if any text shows as boxes.

## Phase 5: docs

- `README.md`: one line saying the GUI follows the Windows display language, which languages exist, and the override key if phase 1 added one.
- `docs/development.md`: add `i18n.py` and `locales/` to the Layout section, and a short "Translate the GUI" task next to the existing translation steps. It should explain how to add a language: copy a catalog, add it to `CATALOGS`, add the language mapping, and add a glossary.
- `AGENTS.md`: add a GUI rule to wrap new user-facing strings with `_()` following the rules in this file, and add the entry to every catalog in the same change.
- Site docs: if phase 1 added a config key, document it in `site/src/content/docs/guide/config-window.md`.

## Adding another language later

After zh-TW ships, each language takes about half a day plus a native review and a layout check. Japanese (`ja`) is the likely next one: the site already has a `ja/` docs folder. Add `locales/ja.py`, an entry in `CATALOGS`, the mapping in language detection, and `docs/i18n/glossary.ja.tsv`.

## Estimate

| Phase | Time |
|---|---|
| 1. Core, detection, catalog check | 0.5 day |
| 2. Wrap strings | 1 day |
| 3. zh-TW catalog | 0.5 day, plus native review |
| 4. Layout pass | 0.5–1 day, plus the user's visual check |
| 5. Docs | 0.25 day |
| Total | 2.75–3.25 days |
