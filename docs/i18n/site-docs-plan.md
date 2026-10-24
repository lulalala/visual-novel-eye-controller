# Site docs translation plan

This plan covers translating the site's guide pages (`site/src/content/docs/guide/`) into another language. It comes from the Traditional Chinese (`zh-tw`) translation; use it for each new language, such as Japanese (`ja`). Read `AGENTS.md` and `site/AGENTS.md` first.

In this plan, `<locale>` is the site's folder name in lowercase (`zh-tw`, `ja`), and `<code>` is the language code the GUI catalog and glossary use (`zh-TW`, `ja`).

## Decisions that carry over

- **English is the source.** Each translated page has the same filename, `sidebar.order` and sections as the English page. Don't add, drop or reorder sections. Translate `title`, `description` and the body.
- **Plain voice.** Docs pages have no character voice and no jokes (`site/AGENTS.md`). The homepage's tsundere dialog doesn't apply here.
- **Terms come from the glossary** `docs/i18n/glossary.<code>.tsv`. Add a row when you settle on a new term.
- **GUI labels match the GUI catalog.** When a page names a button, menu, tab or column, copy the string from `src/eyeokuri/locales/<code>.py`, so readers find it on screen.
- **Identifiers and quoted output stay as in the app.** Keep gesture names (`blink`), config keys (`log_rejected`), signal names, key names, units in code, and log lines or error messages in English. The app keeps them in English, so the page must too. Explain them in the target language.
- **Third-party software stays English.** Skip `third-party.md` and let the fallback show the English page.
- **A native speaker reviews before release.** Say so in the commit body.

## Order of work

Each step depends on the one before it.

1. **GUI catalog and glossary first.** The pages quote GUI labels, and the screenshots show them. If `locales/<code>.py` doesn't exist, do the GUI translation first (`docs/i18n/gui-plan.md`). Check that `docs/i18n/glossary.<code>.tsv` covers the terms in the zh-TW glossary: gesture, step, wizard, take, edge, fire, near miss, cooldown, head limit, hold, config, log, baseline, threshold, plot, time limit, window, status bar, checkbox, tab, live view, and the Help menu (which is not the docs).
2. **Set up the locale.** In `site/astro.config.mjs`, make sure the language is in `locales`, and add `translations: { "<lang tag>": "<translated Guide>" }` to the sidebar group so the group name is translated.
3. **Take the screenshots** for the language: `.venv\Scripts\python tools\capture_screenshots.py --language <code>`. They go to `site/src/assets/screenshots/<locale>/`. Look at all four before you use them. See "Take the site screenshots" in `docs/development.md`.
4. **Translate the pages**, in this order:
   1. `getting-started`, `main-window`, `config-window` (about 1,100 English words).
   2. `gesture-wizard` and `edit-a-gesture`, which have the most terms.
5. **Check the result**: `npm run build` in `site/` passes, and the sidebar and language picker show the new pages. Then view it with `npm run dev`.
6. **Commit** the screenshots and the pages together, apart from glossary or tooling changes.

## Page rules

- Write each page at `site/src/content/docs/<locale>/guide/<same filename>.md`.
- Links to other guide pages need the locale prefix: `/<locale>/guide/main-window/`. A link to a heading uses the translated heading's anchor.
- Screenshots: from a page at that depth, use `../../../../assets/screenshots/<locale>/<name>.png`. Translate the alt text.
- Put a translated GUI label in bold where the English page does, and keep the English identifier in code font next to it when readers need both (`**眨眼**（`blink`）`).
- Use the language's own punctuation and spacing conventions. Check how the GUI handles them (`_STYLES` in `i18n.py`) and match it.

## Keeping the pages in sync

When you change an English page, update every locale that has content in the same change (`site/AGENTS.md`). When the GUI or its catalog changes, retake the screenshots for every language that has them. To find pages that fell behind, compare the last commit of each English page with its translation:

```sh
git log -1 --format=%cI -- site/src/content/docs/guide/<page>.md
git log -1 --format=%cI -- site/src/content/docs/<locale>/guide/<page>.md
```

## Check before you finish

1. `npm run build` in `site/` passes.
2. Every GUI label in the pages appears in `locales/<code>.py`, and every glossary term is used the same way on every page.
3. The pages have the same sections, links and screenshots as the English ones.
4. The final message lists what you could not check: how the pages look in a browser, and that a native speaker hasn't reviewed the wording.

## Questions to settle with the user at the start

- Who reviews the language? Draft yourself, and let them correct.
- Which pages to skip? The default is `third-party.md` only.
- Does the GUI catalog exist and is its layout checked? If not, the screenshots wait.
- Are there terms with more than one common translation, or a formal or casual register to choose? Ask before you write the glossary rows.
