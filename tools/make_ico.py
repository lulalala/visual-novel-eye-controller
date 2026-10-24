"""Packs the window icon PNGs into one .ico for the Windows executable and installer.

Usage: python tools/make_ico.py OUT.ico

Windows Vista and later read PNG images inside .ico files, so no image library is needed.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

ICONS = Path(__file__).resolve().parents[1] / "src" / "eyeokuri" / "icons"
SIZES = (16, 32, 48, 64, 128)


def make_ico(out: Path) -> None:
    images = [(ICONS / f"eyeokuri-{n}.png").read_bytes() for n in SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries = b""
    for size, data in zip(SIZES, images):
        # Width and height are one byte each; 0 means 256.
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    out.write_bytes(header + entries + b"".join(images))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    make_ico(Path(sys.argv[1]))
