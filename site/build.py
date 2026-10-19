"""Builds the static homepage in site/dist from the files in site/src."""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent
SRC = SITE / "src"
DIST = SITE / "dist"
LOGO = SITE.parent / "logo" / "eye-blink.svg"


def inline_logo() -> str:
    # The logo is inlined so its blink animation can be read with getCurrentTime().
    svg = LOGO.read_text(encoding="utf-8")
    svg = re.sub(r"<\?xml[^>]*\?>\s*", "", svg)
    return svg.replace('width="352" height="352"', 'width="100%" height="100%"', 1)


def build() -> Path:
    html = (SRC / "index.html").read_text(encoding="utf-8")
    html = re.sub(
        r"<!-- @inline (\S+) -->",
        lambda m: (SRC / m.group(1)).read_text(encoding="utf-8").rstrip(),
        html,
    )
    html = html.replace("<!-- @logo -->", inline_logo())
    if "<!-- @" in html:
        raise ValueError("index.html has a marker build.py does not know")
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    (DIST / "index.html").write_text(html, encoding="utf-8")
    shutil.copy(LOGO, DIST / "logo.svg")
    return DIST / "index.html"


if __name__ == "__main__":
    try:
        print(f"Wrote {build()}")
    except (OSError, ValueError) as e:
        sys.exit(f"build failed: {e}")
