"""The GUI's colors and ttk styles, taken from the website so the two look related."""

from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Iterable
from tkinter import font as tkfont
from tkinter import ttk

# The site's tokens (site/src/styles/home.css).
PAPER = "#f8f9ff"
INK = "#2a2850"
INK_SOFT = "#5e5c86"
SAKURA = "#ff6b9a"
SAKURA_SOFT = "#ffd8e5"
SKY = "#cbe4ff"
LILAC = "#e2d8ff"
BUTTER = "#fff1c2"
# Sakura is too light for white text or thin lines, so the accent uses the
# docs theme's darker pink (site/src/styles/docs.css).
ACCENT = "#d9376f"
ACCENT_HOVER = "#c42e62"
ACCENT_PRESSED = "#a8244f"
SURFACE = "#ffffff"
LINE = "#d8d6ec"
TAB = "#eceaf8"

OK = "#1d8a5c"
BAD = "#c2362b"
MUTED = INK_SOFT
GRID = "#ecebf7"
ZERO = "#cdcbe3"
TRACE = INK
GRID_TRACE = "#b8b6d3"
# Plot box colors: the site's hues, dark enough to read as thin lines on white.
STEP_COLORS = ("#2f7dd1", ACCENT, "#1d9a6a", "#7656d4", "#b7790a")

# Monospace fonts that ship with the OS, for the log. The UI font stays the
# system's, which already suits the user's language.
_MONO = ("Cascadia Mono", "Consolas", "SF Mono", "Menlo", "DejaVu Sans Mono")


def pick_family(available: Iterable[str], preferred: Iterable[str]) -> str | None:
    """The first preferred font family that is installed, ignoring case."""
    installed = {f.lower() for f in available}
    return next((f for f in preferred if f.lower() in installed), None)


def check_pixels(size: int, fill: str, border: str, mark: str | None) -> list[list[str]]:
    """A square check box as rows of colors, with an anti-aliased check mark when ``mark`` is set."""
    rows = [[border if x in (0, size - 1) or y in (0, size - 1) else fill for x in range(size)]
            for y in range(size)]
    if mark is None:
        return rows
    points = [(0.24 * size, 0.52 * size), (0.43 * size, 0.70 * size), (0.77 * size, 0.31 * size)]
    half = max(1.0, size / 12)
    for y in range(1, size - 1):
        for x in range(1, size - 1):
            d = min(_segment_distance(x + 0.5, y + 0.5, a, b) for a, b in zip(points, points[1:]))
            cover = min(1.0, max(0.0, half + 0.5 - d))
            if cover > 0:
                rows[y][x] = _mix(fill, mark, cover)
    return rows


def _segment_distance(px: float, py: float, a: tuple[float, float], b: tuple[float, float]) -> float:
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _mix(a: str, b: str, amount: float) -> str:
    ca = [int(a[k:k + 2], 16) for k in (1, 3, 5)]
    cb = [int(b[k:k + 2], 16) for k in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * amount) for x, y in zip(ca, cb))


def _check_indicator(root: tk.Tk, style: ttk.Style) -> None:
    """Replaces clam's check box, whose ✕ reads as "off", with a check mark."""
    size = max(13, round(tkfont.nametofont("TkDefaultFont").metrics("linespace") * 0.8))

    def image(fill: str, border: str, mark: str | None) -> tk.PhotoImage:
        img = tk.PhotoImage(master=root, width=size, height=size)
        img.put(" ".join("{" + " ".join(row) + "}" for row in check_pixels(size, fill, border, mark)))
        return img

    off = image(SURFACE, LINE, None)
    states = (
        ("disabled", "selected", image(LINE, LINE, PAPER)),
        ("disabled", image(PAPER, LINE, None)),
        ("selected", image(ACCENT, ACCENT, "#ffffff")),
        ("active", image(SURFACE, SAKURA, None)),
    )
    # Tk drops an image that Python no longer references.
    root.eyeokuri_check_images = (off, states)  # type: ignore[attr-defined]
    style.element_create("Check.indicator", "image", off, *states, sticky="w", width=size + 6)
    style.layout("TCheckbutton", [("Checkbutton.padding", {"sticky": "nswe", "children": [
        ("Check.indicator", {"side": "left", "sticky": ""}),
        ("Checkbutton.focus", {"side": "left", "sticky": "w", "children": [
            ("Checkbutton.label", {"sticky": "nswe"})]})]})])


def apply(root: tk.Tk) -> None:
    """Styles every window. Call it before creating widgets, since plain Tk
    widgets read their colors from the option database when created."""
    mono = pick_family(tkfont.families(root), _MONO)
    if mono is not None:
        tkfont.nametofont("TkFixedFont").configure(family=mono)
    tkfont.nametofont("TkHeadingFont").configure(weight="bold")

    root.configure(background=PAPER)
    for pattern, value in (
        ("*Toplevel.background", PAPER),
        ("*Text.background", SURFACE), ("*Text.foreground", INK),
        ("*Text.selectBackground", SAKURA_SOFT), ("*Text.selectForeground", INK),
        ("*Text.insertBackground", INK),
        ("*Listbox.background", SURFACE), ("*Listbox.foreground", INK),
        ("*Listbox.selectBackground", SAKURA_SOFT), ("*Listbox.selectForeground", INK),
        ("*Listbox.highlightThickness", 1), ("*Listbox.highlightColor", ACCENT),
        ("*Listbox.highlightBackground", LINE),
        ("*Listbox.relief", "flat"), ("*Listbox.borderWidth", 0),
        ("*Canvas.background", SURFACE),
    ):
        root.option_add(pattern, value)

    style = ttk.Style(root)
    # clam is on every platform and draws from the colors below, unlike the
    # native themes, which ignore most of them.
    style.theme_use("clam")
    style.configure(
        ".", background=PAPER, foreground=INK, bordercolor=LINE, lightcolor=PAPER, darkcolor=PAPER,
        troughcolor=PAPER, focuscolor=ACCENT, selectbackground=SAKURA_SOFT, selectforeground=INK,
        fieldbackground=SURFACE, insertcolor=INK, arrowcolor=INK_SOFT,
    )
    style.map(".", foreground=[("disabled", GRID_TRACE)])

    style.configure("TButton", background=SURFACE, lightcolor=SURFACE, darkcolor=SURFACE,
                    padding=(10, 4), anchor="center")
    style.map("TButton",
              background=[("disabled", PAPER), ("pressed", SAKURA_SOFT), ("active", "#fff0f5")],
              lightcolor=[("disabled", PAPER), ("pressed", SAKURA_SOFT), ("active", "#fff0f5")],
              darkcolor=[("disabled", PAPER), ("pressed", SAKURA_SOFT), ("active", "#fff0f5")],
              bordercolor=[("disabled", LINE), ("focus", ACCENT), ("active", SAKURA)])
    # The one loud button per window: Pause, Save, the wizard's Next.
    style.configure("Accent.TButton", background=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT,
                    bordercolor=ACCENT, foreground="white", focuscolor="white")
    style.map("Accent.TButton",
              background=[("disabled", LINE), ("pressed", ACCENT_PRESSED), ("active", ACCENT_HOVER)],
              lightcolor=[("disabled", LINE), ("pressed", ACCENT_PRESSED), ("active", ACCENT_HOVER)],
              darkcolor=[("disabled", LINE), ("pressed", ACCENT_PRESSED), ("active", ACCENT_HOVER)],
              bordercolor=[("disabled", LINE), ("pressed", ACCENT_PRESSED), ("active", ACCENT_HOVER)],
              foreground=[("disabled", PAPER)])

    for widget in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(widget, padding=4, lightcolor=SURFACE, darkcolor=SURFACE)
        style.map(widget, bordercolor=[("focus", ACCENT)], lightcolor=[("focus", SAKURA_SOFT)],
                  fieldbackground=[("disabled", PAPER), ("readonly", SURFACE)])
    style.map("TCombobox", background=[("active", "#fff0f5")])
    root.option_add("*TCombobox*Listbox.background", SURFACE)
    root.option_add("*TCombobox*Listbox.selectBackground", SAKURA_SOFT)
    root.option_add("*TCombobox*Listbox.selectForeground", INK)

    style.configure("TRadiobutton", indicatorbackground=SURFACE, indicatorforeground=ACCENT,
                    upperbordercolor=LINE, lowerbordercolor=LINE)
    style.map("TRadiobutton", background=[("active", PAPER)],
              indicatorbackground=[("disabled", PAPER), ("pressed", SAKURA_SOFT)])
    _check_indicator(root, style)

    style.configure("TNotebook", background=PAPER, bordercolor=LINE, tabmargins=(8, 6, 8, 0))
    style.configure("TNotebook.Tab", background=TAB, lightcolor=TAB, bordercolor=LINE,
                    padding=(14, 5), foreground=INK_SOFT)
    style.map("TNotebook.Tab",
              background=[("selected", PAPER), ("active", "#fff0f5")],
              lightcolor=[("selected", ACCENT), ("active", "#fff0f5")],
              foreground=[("selected", INK)])

    style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, bordercolor=LINE)
    style.map("Treeview", background=[("selected", SAKURA_SOFT)], foreground=[("selected", INK)])
    style.configure("Treeview.Heading", background=TAB, lightcolor=TAB, darkcolor=TAB, relief="flat")
    style.map("Treeview.Heading", background=[("active", "#fff0f5")])

    style.configure("TScrollbar", background=TAB, lightcolor=TAB, darkcolor=TAB, bordercolor=PAPER,
                    troughcolor=PAPER, gripcount=0)
    style.map("TScrollbar", background=[("pressed", LILAC), ("active", LILAC)])
