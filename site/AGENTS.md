# site/AGENTS.md

The public website: a custom homepage (`src/components/Home.astro`, text in `src/i18n/home.ts`, demo in `src/scripts/home.js`) plus Starlight docs in `src/content/docs/`. Readers are visual novel fans deciding whether to download eyeokuri.

## Voice

- **Homepage: playful.** The demo dialog speaks as a tsundere visual novel character (stammers, "It's not like…", "idiot!"), and jokes are welcome. Each line still carries one real fact (blink → `Enter`, head shake pauses, nothing leaves your PC). The voice is the site's hook, so don't flatten it into product copy.
- **Docs pages: plain.** They follow the root docs standard; no character voice or jokes.

## Translations

- When you change English text, update every locale that already has content (`home.ts` and under `src/content/docs/<locale>/`) in the same change, so no locale goes stale.
- Translate the homepage dialog into the same tsundere register in the target language (for `ja`, natural ツンデレ speech, not a literal rendering).

## Check

Run `npm run build` in `site/` and say it passed. Say that you could not check the rendered look; the user must view it with `npm run dev`.
