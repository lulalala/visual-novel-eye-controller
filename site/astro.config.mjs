// Config for the eyeokuri site: a custom homepage plus Starlight docs.
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

export default defineConfig({
  // Set `site` to the public address once the site is hosted, so sitemaps and hreflang links are absolute.
  vite: { server: { fs: { allow: [".."] } } }, // the homepage inlines ../logo/eye-blink.svg
  integrations: [
    starlight({
      title: "eyeokuri",
      favicon: "/logo.svg",
      social: [
        { icon: "github", label: "GitHub", href: "https://github.com/lulalala/visual-novel-eye-controller" },
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
      sidebar: [{ label: "Guide", translations: { ja: "ガイド", "zh-TW": "使用說明" }, items: [{ autogenerate: { directory: "guide" } }] }],
    }),
  ],
});
