# site/AGENTS.md

The public website: a custom homepage (`src/components/Home.astro`, text in `src/i18n/home.ts`, demo in `src/scripts/home.js`) plus Starlight docs in `src/content/docs/`. Readers are visual novel fans deciding whether to download eyeokuri.

## Voice

- **Homepage demo dialog: tsundere.** Only the demo's dialog lines (`lines` in `home.ts`) speak as a tsundere visual novel character (stammers, "It's not like…", "idiot!"). Each line still carries one real fact (blink → `Enter`, head shake pauses, nothing leaves your PC). The voice is the site's hook, so don't flatten it into product copy.
- **Rest of the homepage: casual.** Hero, sections, steps and footer have no character voice, but jokes are welcome. Keep privacy and install facts (trust bullets, the Windows warning steps) plain so readers can trust them.
- **Docs pages: plain.** They follow the root docs standard; no character voice or jokes.

## Translations

- When you change English text, update every locale that already has content (`home.ts` and under `src/content/docs/<locale>/`) in the same change, so no locale goes stale.
- Screenshots show the GUI in its own language. Retake them with `tools/capture_screenshots.py` (see `docs/development.md`) whenever the GUI or its catalog changes; don't reuse English ones in a translated page.
- Translate the homepage dialog into the same tsundere register in the target language (for `ja`, natural ツンデレ speech, not a literal rendering).

## Check

Run `npm run build` in `site/` and say it passed. Say that you could not check the rendered look; the user must view it with `npm run dev`.
