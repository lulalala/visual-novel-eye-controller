"""Builds the static homepage in site/dist from the files in site/src."""

from __future__ import annotations

import re
import shutil
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
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


class RebuildHandler(SimpleHTTPRequestHandler):
    # Rebuilds on every page load, so a browser refresh shows your last edit.
    def do_GET(self) -> None:
        if self.path.split("?")[0] in ("/", "/index.html"):
            try:
                build()
            except (OSError, ValueError) as e:
                print(f"build failed: {e}")
        super().do_GET()


def serve(port: int) -> None:
    build()
    handler = partial(RebuildHandler, directory=str(DIST))
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"Serving http://localhost:{port}/ (Ctrl+C to stop)")
        server.serve_forever()


if __name__ == "__main__":
    try:
        if "--serve" in sys.argv:
            serve(8000)
        else:
            print(f"Wrote {build()}")
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError) as e:
        sys.exit(f"build failed: {e}")
