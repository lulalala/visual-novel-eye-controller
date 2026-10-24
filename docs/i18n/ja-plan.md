# Japanese translation plan

This plan covers adding Japanese (`ja`) to eyeokuri: the GUI first, then the website. The translation setup is already built and has shipped Traditional Chinese (`zh-TW`), so adding a language is mostly filling in a catalog and updating a few lists. Follow the zh-TW work as the example; `git log --oneline -- src/eyeokuri/locales docs/i18n site/src/content/docs/zh-tw` lists its commits.

Read these first:

- `AGENTS.md`: the hard rules, the GUI layout rules and the definition of done.
- `docs/i18n/gui-plan.md`, section "Rules for every translatable string": how GUI strings are written and why. Don't change those rules for Japanese.
- `docs/development.md`, sections "Translate the GUI", "Translate the site" and "Take the site screenshots".
- `site/AGENTS.md` before you touch `site/`.

Commit only when the user asks. Before you amend or fold a fix into a commit, check `git log -1` shows your commit: the user commits between sessions.

## Decisions the user already made

- Log lines, trigger reasons (`blink: step 2 came 0.12s after step 1 ...`) and `ValueError` messages stay in English, in the GUI too. The gesture window and wizard show an English reason after a translated label; that mix is expected.
- Strings have no `{name}` placeholders. Values sit after the sentence, after a colon or on their own line, so a translation never reorders them.
- The GUI follows the Windows display language, and `app.language` overrides it. The Language dropdown on the config window's General tab sets it. The language changes when the GUI restarts.
- The command line stays English.

## Decisions to ask the user about

Ask before you start:

1. **Register.** The suggestion is です/ます for full sentences and plain noun phrases for buttons and labels (`保存`, `キャンセル`), as Windows does. A more casual tone would match the site's voice but not other Windows apps.
2. **Core terms.** Settle these with the user and record them in the glossary before you fill the catalog. Suggested starting points, none confirmed yet:

   | English | Suggestion | Question |
   |---|---|---|
   | gesture | ジェスチャー | Fine for face movements in Japanese, unlike 手勢 in Chinese? |
   | take (one recording in the wizard) | テイク or 録画 | テイク reads as film jargon; 録画 is plainer |
   | fire (a gesture fires) | 反応する or 発動する | |
   | step | ステップ | |
   | wizard | ウィザード | |
   | webcam / camera | Webカメラ / カメラ | |
   | near miss (too-quick or too-slow take) | — | Needs a natural phrase; the GUI shows "Too quick" and "Too slow" |

3. **Scope.** GUI only, or the website too (homepage and guide pages). The site already lists 日本語 in its language menu (`site/astro.config.mjs`) but has no Japanese pages yet.

## Add Japanese to the GUI

Make these changes together, in one commit. The catalog test rejects a catalog that is partly filled, and any code in `CATALOGS` shows in the Language dropdown and becomes a valid `app.language` value, so don't register `ja` until its catalog is complete.

1. **Glossary.** Add `docs/i18n/glossary.ja.tsv` with the columns of `glossary.zh-TW.tsv` (`en`, `ja`, `note`). Copy the English terms from the zh-TW file, so the same concepts get settled, and add the decisions above. Keep its rules for what stays Latin: `eyeokuri` (lowercase), key names (`Enter`, `ctrl+s`), gesture names, config keys, signal names, units.
2. **Catalog.** Copy `src/eyeokuri/locales/zh_tw.py` to `src/eyeokuri/locales/ja.py`. Translate each value from the English key, not from the Chinese value. Change the docstring to name Japanese and `glossary.ja.tsv`, and keep the line saying a native speaker hasn't reviewed it.
3. **Register the language** in `src/eyeokuri/i18n.py`:
   - `CATALOGS`: add `"ja": ja.CATALOG` and the import.
   - `_LOCALE_LANGUAGES`: add `"ja_JP": "ja"`. Windows reports LANGID `0x0411`, which `locale.windows_locale` maps to `ja_JP`.
   - `_STYLES`: add `"ja": ("", "。")`. Japanese has no space between sentences and ends a sentence with 。. Fit notes and wizard messages join sentences with `gap()` and end values with `stop()`.
   - `LANGUAGE_NAMES`: add `"ja": "日本語"`.
4. **Tests:**
   - `tests/test_i18n.py`: the locale mapping case `("ja_JP", "en")` becomes `("ja_JP", "ja")`. Add `ja` to `test_sentence_gap_and_stop_follow_the_language`. The catalog checks cover `ja` by themselves, since they run for every code in `CATALOGS`.
   - `tests/test_config.py`: add `app.language=ja` to `test_language_can_be_set_through_set`, and update the allowed list in the `match=` of `test_unknown_language_is_rejected` (`auto, en, ja, zh-TW`).
5. **Language lists in text.** Update each place that lists languages:
   - `README.md`: the paragraph on the GUI language (Japanese, the `language = "ja"` example).
   - `config.example.toml` and the `AppConfig` comment in `src/eyeokuri/config.py`: the `"en" or "zh-TW"` comments. Comments only; the default stays `"auto"`, and `app.language` accepts `ja` once it's in `CATALOGS`.
   - `docs/development.md`: the "Translate the GUI" paragraph that names the catalogs, and `locales/` in the Layout section.
   - `tools/capture_screenshots.py`: the `--language` help text.

### Writing the Japanese strings

- **Full-width punctuation** inside translated strings: `：` `、` `。` `（）` `？`. Each English key that ends in a colon (`"Now:"`) gets `：` (`"現在："`), since the value follows it in code.
- **Leave strings that are only a noun before a number short**: `_("Step")` + ` 2` reads `ステップ 2`. Don't add 目 or 番, because code appends the number.
- **Keep the space or newline layout of the English key.** A key such as `"Delete this gesture?\n\n"` keeps its `\n\n`. Code adds the value after it.
- **Trailing spaces.** Some keys end in a space because code joins them to the next piece. Keep them only where the joined text needs a space. Check the source line for the key before you drop one.
- **Length.** Japanese is usually as short as English or shorter, but katakana loanwords (`キャリブレーション中…`) can be long. Phase 4 of `gui-plan.md` lists the fixed widths that can clip.

### Check

- `.venv\Scripts\python -m pytest -q` passes.
- `.venv\Scripts\eyeokuri --help` and `.venv\Scripts\eyeokuri-gui --help` run. (`--help` exits before the config is checked, so it doesn't test `app.language`; the config tests above do.)

You can't see the windows. Ask the user to start the GUI with Japanese (Language dropdown, or `language = "ja"` under `[app]` in `config.toml`) and check each window by eye: main window, config window (both tabs), gesture window, camera picker, wizard take page and review page, About.

Ask them to check one extra thing for Japanese: **kanji glyph shapes.** Tk keeps the system UI font and falls back to another font for characters it lacks. On a Japanese Windows that fallback is a Japanese font. On an English or Chinese Windows with `language = "ja"`, kanji might render in a Chinese font, with shapes that look wrong to a Japanese reader (for example 直 and 骨). If they do, ask the user before changing fonts: the fix is choosing a Japanese UI font (`Yu Gothic UI`, `Meiryo UI`) for `TkDefaultFont` when the language is `ja`, the way `theme.py` picks the log's monospace font with `pick_family`.

Say in the commit body and the final message that a native speaker must review the catalog before release.

## Add Japanese to the website

Only do this if the user wants the site translated (decision 3). The steps match the zh-TW site commits.

1. **Screenshots.** Run `.venv\Scripts\python tools\capture_screenshots.py --language ja`. It saves to `site/src/assets/screenshots/ja/`. It needs Windows and the Japanese GUI catalog, so do the GUI first. Look at the images before you commit them, and ask the user to check them too.
2. **Guide pages.** Copy each page from `site/src/content/docs/guide/` to `site/src/content/docs/ja/guide/` and translate it. Use `site/src/content/docs/zh-tw/guide/` as the example of what stays English (log lines and error messages quoted in pages) and how translated pages reference their screenshots. Button and window names in the text must match the Japanese catalog exactly, because readers look for them on screen.
3. **Sidebar.** Add `"ja"` to the sidebar group's `translations` in `site/astro.config.mjs`.
4. **Homepage.** Add a `ja` entry to `site/src/i18n/home.ts` and `site/src/pages/ja/index.astro` rendering `<Home locale="ja" />`, as for `zh-tw`. The demo dialog lines are written as a tsundere character; `site/AGENTS.md` asks for natural ツンデレ speech in Japanese, not a literal rendering of the English.
5. **Glossary.** Add rows for any new terms the pages need (the zh-TW site work added log, baseline, threshold, plot, time limit, status bar, tab, live view and the Help menu).
6. **Check.** Run `npm run build` in `site/` and say it passed. You can't check how the pages look; the user views them with `npm run dev`.

From then on, `site/AGENTS.md` requires that an English text change updates `ja` in the same change.

## Keep it working

After Japanese ships, each GUI string change touches both catalogs. `tests/test_i18n.py` fails when a catalog is missing an entry or has one that is no longer in the source. Changing an English key invalidates its translations, so retranslate the entry in `ja.py` and `zh_tw.py`, not only the English. When the GUI changes, retake the screenshots for every language that has them.

## Estimate

| Work | Time |
|---|---|
| Glossary and term decisions with the user | 0.25 day |
| GUI catalog (about 200 entries) and registration | 0.5 day |
| User's visual check and fixes | 0.25 day |
| Website: screenshots, five guide pages, homepage | 1 day |
| Native review | Outside the agent's work; required before release |
