# GUI translation plan

This plan covers translating the `eyeokuri-gui` windows into any language. Traditional Chinese (Taiwan, `zh-TW`) was first and Japanese (`ja`) followed; both use the same setup. Phases 0-2 and 5 built the shared machinery and are done. To add another language, follow "Add a language" below. Work through the phases in order when you build new machinery; each phase is one commit. Read `AGENTS.md` first: its rules (no new runtime dependencies, tests without Tk or a camera, column-aligned layout) apply to every phase.

## Status

| Phase | State |
|---|---|
| 0. Reword sentences so values sit outside them | Done in `f676b45` |
| 1. Translation core and language choice | Done, with the `app.language` key |
| 2. Wrap the GUI strings | Done: about 200 strings |
| 3. Language catalogs | `zh-TW` and `ja` done, awaiting native review |
| 4. Layout pass | Code done; waiting for the user's visual check |
| 5. Docs | Done |

Update this table when you finish a phase.

## Scope

The GUI has about 230 user-facing strings and 1,200 words, in `src/eyeokuri/gui/*.py` and `src/eyeokuri/tuning.py` (wizard prompts and fit notes).

Language-specific examples below use `zh-TW` and `ja`; the rules apply to every language.

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
- Identifiers: names of gestures you add, config keys on the Advanced tab (`baseline_window_s`), key names (`Enter`, `ctrl+s`) and units (`s`, `°`). Built-in gestures and signals are the exception: `labels.py` shows a translated label followed by the ID (`まばたき（blink）`), so you can still find the ID in the log and config file. Show a gesture or signal ID with `show_gesture()` or `show_signal()`, and a combobox of IDs with `id_box()` in `gui/tkutil.py`.
- `config.example.toml` and the comments written by `dump_config()`.

## Rules for every translatable string

Phase 0 already rewrote the sentences to follow these rules. Keep new strings to them too.

1. **Only literals go into the catalog.** `_()` takes a plain string literal, never an f-string or a variable. Put the changeable part outside: `_("Recorded:") + f" {t:.1f} s"`.
2. **Values go after the sentence, not inside it.** Use a label ending in a colon (`Now: 0.62`), or a sentence followed by the value on its own line (`Delete this gesture?\n\nblink`). Don't add `{name}` placeholders.
3. **A noun followed by a number is fine**: `Step 2`, `Take 2 / 5`, `Camera 1`. Translate the noun (`_("Step")`) and append the number.
4. **Each branch of a conditional is its own complete string.** Write `_("Couldn't turn on this gesture:") if enabled else _("Couldn't turn off this gesture:")`, never `"turn " + ("on" if enabled else "off")`.
5. **Punctuation belongs to the translated string.** Include the colon in `_("Now:")`, so zh-TW and ja can use a full-width `：`. Where code joins sentences or ends one after a value, use `gap()` and `stop()` from `i18n.py` instead of `" "` and `"."`, `aside()` for parentheses after a word, and `colon()` after a label built in code; they follow the language's `_STYLES` entry. Don't capitalize, lowercase or add a period to a translated string in code (`.capitalize()`, `[:1].upper()`); store it the way it's shown.
6. **No plural forms.** Write counts as a label: `Too-slow takes that still fire: 2.`
7. **Mark strings in module-level constants with `N_()`** (returns its argument unchanged) and call `_(value)` where you display them. This covers `KIND_LABELS`, `SIGNAL_PLOTS` hints, `_GENERAL_HELP`, `suggestions()` and section headings. Constants are built at import time, before the language is set, so `_()` in a constant would always return English.

## Phase 1: translation core and language choice

Add `src/eyeokuri/i18n.py`. It has no Tk imports, because `tuning.py` uses it too.

- `_(text)` returns the active catalog's translation, or `text` when the entry is missing or the language is English. `N_(text)` returns `text`.
- `set_language(code)` picks the catalog. Call it once in `gui/launch.py` before any window is built. The language changes only when the GUI restarts.
- Catalogs are plain Python dicts, `{"English text": "translated text"}`, one module per language (`locales/zh_tw.py`, `locales/ja.py`). Import them statically from `i18n.py` (a `CATALOGS` dict), so PyInstaller bundles them without `hiddenimports` or `--add-data`. Don't use stdlib `gettext`: it needs compiled `.mo` files and adds a build step.
- Three tables in `i18n.py` describe a language, besides its catalog:
  - `_LOCALE_LANGUAGES` maps Windows locale names to a catalog code (`ja_JP` → `ja`, `zh_TW` and `zh_HK` → `zh-TW`). A locale with no entry gets English.
  - `_STYLES` holds a `_Style`: the gap between sentences, the full stop, an aside after a word and the colon after a label. The default is `_Style(" ", ".", " ({})", ": ")`; Chinese and Japanese use `_Style("", "。", "（{}）", "：")`.
  - `LANGUAGE_NAMES` holds the language's name in itself for the Language dropdown (`日本語`). It is never translated.
- Detect the language from the Windows UI language. Call `ctypes.windll.kernel32.GetUserDefaultUILanguage()` lazily inside a function, and map the LANGID with `locale.windows_locale` (`0x0404` → `zh_TW`). Fall back to English on other platforms or unknown languages. Match the region: `zh_CN` gets English until there's a `zh-CN` catalog.
- The CLI never calls `set_language()`, so it stays English.

The user chose to add a config key that overrides detection (done): `app.language = "auto"` (`"auto"`, `"en"` or a catalog code). It needs the usual steps: the default in `AppConfig`, the same value in `config.example.toml`, validation in the constructor with a `ValueError` listing allowed values, and a check that `--set app.language=en` works. Adding the key doesn't change what old files mean, so don't bump `CONFIG_VERSION`.

Add `tests/test_i18n.py`:

- `_()` falls back to the English text when an entry is missing, and when no language is set.
- Language detection maps every locale in `_LOCALE_LANGUAGES`, a locale with no catalog (`zh_CN`) and an unknown code correctly. Test the mapping function with a code string; don't call Windows APIs in tests.
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

## Phase 3: language catalogs

Fill `src/eyeokuri/locales/<module>.py` with every entry the Phase 1 check lists. Translate from the English key, not from another language's value.

- Use the terms in `docs/i18n/glossary.<code>.tsv`. Settle the core terms with the user first (gesture, step, wizard, webcam, frame, take, edge, fire, near miss, baseline, cooldown, head limit) and add a row for each new GUI term.
- Match the tone of that language's site homepage in `site/src/i18n/home.ts`, unless the user picks a register for the GUI (for `ja`, です/ます sentences and plain noun phrases for buttons, as Windows does).
- Keep identifiers, units and key names in Latin, as the glossary says.
- Use the language's own punctuation inside translated strings (full-width `：`, `，`, `。`, `？` for Chinese and Japanese).
- A key that ends in a colon, a space or `\n\n` keeps that ending, because code appends the value. Check the source line before you drop a trailing space.

A native speaker must review the catalog before release. Say so in the commit body.

## Phase 4: layout pass

Translated text changes widths, and the GUI rules require column-aligned layout. Check these places, where a fixed size might clip or misalign text:

- `wraplength` values: 640 (config and gesture windows), 380 (config help), `_WIZARD_WRAP = 760` (wizard).
- Fixed widths: wizard review columns 170 and 340 (`wizard.py`), the **Record** button `width=12`, comboboxes `width=18`, `✕` buttons `width=3`.
- The plot's `Fires:` label, which flips sides at `width - 90` (`plot.py`).
- Main window column headings and the status bar.

Agents can't see the windows. Make the code changes this list needs (for example, a width from text measurement instead of a constant), then list every window for the user to check by eye with `zh-TW` active: main window, config window (both tabs), gesture window, camera picker, wizard take page and review page, About. Fonts: Tk on Windows falls back to a CJK font for Segoe UI by itself; report if any text shows as boxes.

## Phase 5: docs

- `site/src/content/docs/guide/config-window.md` (all locales): one line saying the GUI follows the Windows display language, which languages exist, and the override key if phase 1 added one.
- `docs/development.md`: add `i18n.py` and `locales/` to the Layout section, and a short "Translate the GUI" task next to the existing translation steps that points here for how to add a language.
- `AGENTS.md`: add a GUI rule to wrap new user-facing strings with `_()` following the rules in this file, and add the entry to every catalog in the same change.
- Site docs: if phase 1 added a config key, document it in `site/src/content/docs/guide/config-window.md`.

## Add a language

Each language takes about half a day plus a native review and a layout check. Make these changes together, in one commit. The catalog test rejects a partly filled catalog, and any code in `CATALOGS` shows in the Language dropdown and becomes a valid `app.language` value, so don't register a language until its catalog is complete.

1. **Ask the user** for the register (formal or casual) and the core terms (Phase 3), and whether the website gets translated too.
2. **Glossary.** Add `docs/i18n/glossary.<code>.tsv` with the columns of the existing ones (`en`, the language, `note`). Copy the English terms from another glossary so the same concepts get settled.
3. **Catalog.** Copy an existing `locales/*.py` to `locales/<module>.py` (lowercase, underscores: `zh_tw.py`) and translate every value. Name the language and glossary in the docstring, and keep the line saying a native speaker hasn't reviewed it.
4. **Register it** in `src/eyeokuri/i18n.py`:
   - `CATALOGS`: the import and `"<code>": <module>.CATALOG`.
   - `_LOCALE_LANGUAGES`: every Windows locale name that should get it (`locale.windows_locale` values, such as `ja_JP`).
   - `_STYLES`: only if sentences aren't joined by a space and ended by `.`, or asides and colons aren't ` (…)` and `: `.
   - `LANGUAGE_NAMES`: the language's name in itself.
5. **Tests.** `tests/test_i18n.py` checks every code in `CATALOGS` by itself. Add the locale cases to the mapping test, and the code to `test_sentence_gap_and_stop_follow_the_language` if it has a `_STYLES` entry. In `tests/test_config.py`, add `app.language=<code>` to `test_language_can_be_set_through_set` and update the allowed list in `test_unknown_language_is_rejected`.
6. **Text that lists languages:** `site/src/content/docs/guide/config-window.md` (the language section and the `language = "<code>"` example), the `app.language` comments in `config.example.toml` and `AppConfig`, the Layout and "Translate the GUI" text in `docs/development.md`, and the `--language` help in `tools/capture_screenshots.py`. The default stays `"auto"`.
7. **Layout check.** Run Phase 4 for the new language and ask the user to look at every window. Check script-specific rendering too: for CJK languages, Tk falls back to another font for glyphs the UI font lacks, so on a system whose Windows language differs, shared Han characters can render with the wrong regional shapes (for `ja`, 直 and 骨). If they do, ask before changing fonts; the fix is choosing a UI font for that language, the way `theme.py` picks the log font with `pick_family`.
8. **Website (optional).** Follow "Translate the site" in `docs/development.md` and `site/AGENTS.md`: screenshots with `tools/capture_screenshots.py --language <code>`, guide pages, sidebar `translations`, and a `site/src/i18n/home.ts` entry.

The setup doesn't cover right-to-left scripts (the layout would need work) or languages that need plural forms or reordered values (rules 2 and 6 avoid both for now). Raise those with the user before starting.

## Keep it working

Each GUI string change touches every catalog. `tests/test_i18n.py` fails when a catalog is missing an entry or has one that is no longer in the source. Changing an English key invalidates its translations, so retranslate the entry in every catalog, not only the English. When the GUI changes, retake the screenshots for every language that has them.

## Estimate

| Phase | Time |
|---|---|
| 1. Core, detection, catalog check | 0.5 day |
| 2. Wrap strings | 1 day |
| 3. One language catalog | 0.5 day, plus native review |
| 4. Layout pass | 0.5–1 day, plus the user's visual check |
| 5. Docs | 0.25 day |
| Total for the first language | 2.75–3.25 days |
| Each further language | About 1 day without the website, plus native review |
