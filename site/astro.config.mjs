// Config for the eyeokuri site: a custom homepage plus Starlight docs.
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

export default defineConfig({
  // Hosted on GitHub Pages as a project site; with a custom domain, set `site` to it and remove `base`.
  site: "https://lulalala.github.io",
  base: "/eyeokuri",
  vite: { server: { fs: { allow: [".."] } } }, // the homepage inlines ../logo/eye-blink.svg
  integrations: [
    starlight({
      title: "eyeokuri",
      favicon: "/logo.svg",
      social: [
        { icon: "github", label: "GitHub", href: "https://github.com/lulalala/eyeokuri" },
      ],
      // To translate: add content under src/content/docs/<locale>/ and a home page under src/pages/<locale>/.
      // Pages without a translation fall back to English with a notice.
      defaultLocale: "root",
      locales: {
        root: { label: "English", lang: "en" },
        ja: { label: "日本語", lang: "ja" },
        "zh-tw": { label: "繁體中文", lang: "zh-TW" },
      },
      customCss: ["./src/styles/docs.css"],
      head: [
        { tag: "link", attrs: { rel: "preconnect", href: "https://fonts.googleapis.com" } },
        { tag: "link", attrs: { rel: "preconnect", href: "https://fonts.gstatic.com", crossorigin: "" } },
        { tag: "link", attrs: { rel: "stylesheet", href: "https://fonts.googleapis.com/css2?family=Zen+Maru+Gothic:wght@500;700;900&family=JetBrains+Mono:wght@500&display=swap" } },
      ],
      sidebar: [{ label: "Guide", translations: { ja: "ガイド", "zh-TW": "使用說明" }, items: [{ autogenerate: { directory: "guide" } }] }],
    }),
  ],
});
