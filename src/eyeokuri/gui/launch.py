"""Starts the GUI."""

from __future__ import annotations

import argparse
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from eyeokuri import theme
from eyeokuri.config import Config, load_config
from eyeokuri.engine import check_config
from eyeokuri.gui.main_window import MainWindow


def _windows_sharp_text() -> None:
    """Without this, Windows scales the window up as a bitmap on high-DPI screens, so text looks blurry."""
    if sys.platform == "win32":
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="eyeokuri-gui", description="eyeokuri with a window: live view, log and settings.")
    p.add_argument("-c", "--config", type=Path, default=Path("config.toml"),
                   help="config file to load and save (default: config.toml, created on first save)")
    args = p.parse_args(argv)
    _windows_sharp_text()
    root = tk.Tk()
    theme.apply(root)
    try:
        config = load_config(args.config) if args.config.exists() else Config()
        check_config(config)
    except (ValueError, OSError) as e:
        root.withdraw()
        messagebox.showerror("eyeokuri", f"Can't load {args.config}:\n\n{e}")
        root.destroy()
        return 2
    MainWindow(root, config, args.config)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
