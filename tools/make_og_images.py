"""Renders the homepage link-preview cards (1200x630) with headless Microsoft Edge.

Usage: python tools/make_og_images.py

Reads the headline and tagline of each language from site/src/i18n/home.ts and writes
site/public/og.png (English) and site/public/og-<language>.png. Needs Edge and an internet
connection (for the Zen Maru Gothic web font). Look at the images before you commit them.
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME_TS = ROOT / "site" / "src" / "i18n" / "home.ts"
LOGO = ROOT / "logo" / "eye-static.svg"
OUT = ROOT / "site" / "public"
EDGES = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)

# Headline size per language, so the longest line stays clear of the eye.
HEADLINE_PX = {"en": 128, "ja": 88, "zh-TW": 110}

PAGE = """<!doctype html><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zen+Maru+Gothic:wght@500;900&display=swap">
<style>
html, body {{ margin: 0 }}
body {{ width: 1200px; height: 630px; background: #F8F9FF; color: #2A2850; display: flex; align-items: center;
  gap: 20px; padding: 0 90px; box-sizing: border-box; position: relative; overflow: hidden;
  font-family: {font}; }}
body:before {{ content: ""; position: absolute; right: -120px; top: -140px; width: 620px; height: 620px;
  border-radius: 50%; background: #FFD8E5 }}
body:after {{ content: ""; position: absolute; left: -100px; bottom: -200px; width: 520px; height: 520px;
  border-radius: 50%; background: #CBE4FF }}
.text, .logo {{ position: relative; z-index: 1 }}
.logo {{ width: 360px; height: 360px; flex: none; order: 2 }}
h1 {{ font-size: {size}px; line-height: 1.1; margin: 0; font-weight: 900; white-space: nowrap }}
h1 span {{ color: #FF6B9A }}
p {{ font-size: 34px; margin: 24px 0 0; font-weight: 500 }}
b {{ display: block; margin-top: 28px; font-size: 30px; color: #5E5C86 }}
</style>
<div class="text"><h1>{line1}<br><span>{line2}</span></h1><p>{tagline}</p><b>eyeokuri</b></div>
<div class="logo">{logo}</div>"""


def read_locales() -> dict[str, dict[str, str]]:
    """Returns {language: {lang, heroLine1, heroLine2, sub}} from home.ts."""
    text = HOME_TS.read_text(encoding="utf-8")
    start = text.index("export const home")
    blocks = re.split(r'^  "?([a-z-]+)"?: \{$', text[start:], flags=re.M)[1:]
    locales = {}
    for key, body in zip(blocks[::2], blocks[1::2]):
        locales[key] = {
            f: re.search(rf'^    {f}: "(.*)",$', body, re.M).group(1)
            for f in ("lang", "heroLine1", "heroLine2", "sub")
        }
    return locales


def render(edge: Path, page: str, out: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "og.html"
        src.write_text(page, encoding="utf-8")
        subprocess.run(
            [str(edge), "--headless", "--disable-gpu", "--hide-scrollbars", "--window-size=1200,630",
             "--virtual-time-budget=8000", f"--screenshot={out}", src.as_uri()],
            check=True, capture_output=True,
        )


def main() -> None:
    edge = next((e for e in EDGES if e.exists()), None)
    if edge is None:
        sys.exit("Microsoft Edge not found.")
    logo = re.sub(r"<\?xml[^>]*\?>\s*", "", LOGO.read_text(encoding="utf-8"))
    logo = logo.replace('width="352" height="352"', 'width="100%" height="100%"')
    for key, t in read_locales().items():
        zh = t["lang"] == "zh-TW"
        # The first sentence of the subtitle is the tagline.
        tagline = re.split(r"(?<=[。.])\s*", t["sub"])[0]
        page = PAGE.format(
            font='"Microsoft JhengHei", "PingFang TC", sans-serif' if zh else '"Zen Maru Gothic", "Yu Gothic", sans-serif',
            size=HEADLINE_PX.get(t["lang"], 110),
            line1=html.escape(t["heroLine1"]), line2=html.escape(t["heroLine2"]),
            tagline=html.escape(tagline), logo=logo,
        )
        out = OUT / ("og.png" if key == "en" else f"og-{key}.png")
        render(edge, page, out)
        print(out)


if __name__ == "__main__":
    main()
