"""Tests for the GUI theme's font choice, drawn check box and window icons."""

from __future__ import annotations

import struct
from importlib import resources

from eyeokuri.theme import _ICON_SIZES, ACCENT, LINE, SURFACE, check_pixels, pick_family


def test_pick_family_takes_first_installed_ignoring_case() -> None:
    assert pick_family(["Arial", "consolas", "Menlo"], ["Cascadia Mono", "Consolas", "Menlo"]) == "Consolas"


def test_pick_family_returns_none_when_nothing_is_installed() -> None:
    assert pick_family(["Arial"], ["Consolas"]) is None


def test_unchecked_box_is_border_around_fill() -> None:
    rows = check_pixels(13, SURFACE, LINE, None)
    assert len(rows) == 13 and all(len(r) == 13 for r in rows)
    assert rows[0][6] == LINE and rows[6][0] == LINE and rows[12][12] == LINE
    assert all(c == SURFACE for row in rows[1:-1] for c in row[1:-1])


def test_checked_box_draws_mark_inside_border() -> None:
    rows = check_pixels(16, ACCENT, ACCENT, "#ffffff")
    # The corner of the check sits about 70% down, a little left of center.
    assert rows[11][7] == "#ffffff"
    assert rows[2][2] == ACCENT
    assert all(c == ACCENT for c in rows[0] + rows[-1])


def test_every_icon_size_ships_as_a_square_png() -> None:
    icons = resources.files("eyeokuri") / "icons"
    for size in _ICON_SIZES:
        data = (icons / f"eyeokuri-{size}.png").read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        assert struct.unpack(">II", data[16:24]) == (size, size)
