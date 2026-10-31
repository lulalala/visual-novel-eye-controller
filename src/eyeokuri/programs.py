"""Per-program configs: gesture settings that apply on top of the base config
while a program (a game, a reader) is in front.

A program file stores only the gesture fields that differ from the base config,
so a later change to the base reaches every program that doesn't override it."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

from eyeokuri.config import CONFIG_VERSION, Config, _merge, _toml_value, gesture_lines
from eyeokuri.engine import check_config
from eyeokuri.foreground import Seen

BASE = "base"
PROGRAM = "program"
"""The main window's tabs: the base config, and the program in front."""


@dataclass(frozen=True)
class Program:
    exe: str
    """The executable's file name (``CLANNAD.exe``); matched without regard to case."""
    name: str
    """Shown on the tab."""
    path: Path
    overrides: dict[str, Any] = field(default_factory=dict)
    """``[gestures.NAME]`` tables: what differs from the base config."""
    saved: bool = False
    """It has a file. Until then it is only a "Create for" tab and the base config is in use."""

    @property
    def key(self) -> str:
        return self.exe.lower()


def file_name(exe: str) -> str:
    """``CLANNAD.exe`` -> ``clannad.toml``."""
    stem = exe[:-4] if exe.lower().endswith(".exe") else exe
    return re.sub(r"[^a-z0-9_-]", "_", stem.lower()) + ".toml"


def new_program(folder: Path, seen: Seen, programs: dict[str, Program]) -> Program:
    """A program you haven't made a config for, with a file name no other program uses."""
    taken = {p.path.name.lower() for p in programs.values()}
    name = file_name(seen.exe)
    n = 2
    while name in taken or (folder / name).exists():
        name = f"{file_name(seen.exe)[:-5]}-{n}.toml"
        n += 1
    title = seen.title.strip() or seen.exe
    return Program(exe=seen.exe, name=title, path=folder / name)


def merged(base: Config, program: Program | None) -> Config:
    """The base config with the program's gesture fields over it. An override of a
    gesture the base no longer has, and that doesn't define its steps, is left out."""
    if program is None:
        return base
    return _merge(base, {"gestures": dict(usable(base, program))}, "")


def usable(base: Config, program: Program) -> dict[str, Any]:
    return {name: table for name, table in program.overrides.items()
            if name in base.gestures or "steps" in table}


def stale(base: Config, program: Program) -> list[str]:
    """Gestures the program overrides that are no longer in the base config."""
    return [name for name in program.overrides if name not in usable(base, program)]


def with_gestures(program: Program, base: Config, config: Config) -> Program:
    """The program, overriding whatever ``config``'s gestures change from the base."""
    text = "\n".join(gesture_lines(config.gestures, base.gestures))
    return replace(program, overrides=tomllib.loads(text).get("gestures", {}))


def split(base: Config, program: Program | None, tab: str, config: Config) -> tuple[Config, Program | None]:
    """Where an edit of ``config`` in ``tab`` goes: gestures to that tab's layer,
    everything else (camera, pause, language...) to the base config."""
    if tab == BASE or program is None:
        return config, program
    base = replace(config, gestures=base.gestures)
    return base, with_gestures(program, base, config)


def dump_program(base: Config, program: Program) -> str:
    """The program's file: its exe and name, and the gesture fields that differ from the base config."""
    lines = [f"version = {CONFIG_VERSION}", "", "[program]",
             f"exe = {_toml_value(program.exe)}", f"name = {_toml_value(program.name)}"]
    lines += gesture_lines(merged(base, program).gestures, base.gestures)
    return "\n".join(lines) + "\n"


def load_program(path: Path) -> Program:
    with path.open("rb") as f:
        data = tomllib.load(f)
    version = data.get("version")
    if version != CONFIG_VERSION:
        found = "no version key" if version is None else f"version = {version!r}"
        raise ValueError(f"{path} has {found}; program configs need version = {CONFIG_VERSION}")
    for key in data:
        if key not in ("version", "program", "gestures"):
            raise ValueError(f"{path}: only [program] and [gestures.NAME] sections are allowed, not {key}")
    program = data.get("program")
    if not isinstance(program, dict) or not isinstance(program.get("exe"), str) or not program["exe"]:
        raise ValueError(f'{path} needs a [program] section with exe = "NAME.exe"')
    for key in program:
        if key not in ("exe", "name"):
            raise ValueError(f"{path}: unknown key program.{key}; use exe and name")
    name = program.get("name", program["exe"])
    if not isinstance(name, str):
        raise ValueError(f"{path}: program.name should be str, got {type(name).__name__}")
    gestures = data.get("gestures", {})
    if not isinstance(gestures, dict) or not all(isinstance(t, dict) for t in gestures.values()):
        raise ValueError(f"{path}: each [gestures.NAME] must be a table")
    return Program(exe=program["exe"], name=name, path=path, overrides=gestures, saved=True)


def load_programs(folder: Path, base: Config, log: Callable[[str], None]) -> dict[str, Program]:
    """The program configs in ``folder``, by lowercased exe. A file that can't be
    used is logged and skipped, so one bad file doesn't stop the app."""
    programs: dict[str, Program] = {}
    for path in sorted(folder.glob("*.toml")) if folder.is_dir() else []:
        try:
            program = load_program(path)
            check_config(merged(base, program))
        except (ValueError, OSError, tomllib.TOMLDecodeError) as e:
            log(f"Ignored {path}: {e}")
            continue
        if program.key in programs:
            log(f"Ignored {path}: {programs[program.key].path} is already the config for {program.exe}")
            continue
        for name in stale(base, program):
            log(f"gestures.{name} in {path}: not in the base config, ignored")
        programs[program.key] = program
    return programs


def next_target(previous: Program | None, seen: Seen | None, programs: dict[str, Program],
                folder: Path) -> Program | None:
    """The program the second tab is for, after ``seen`` came to the front.

    eyeokuri's own windows and the shell (Alt+Tab, the taskbar) keep the previous
    one, so you can switch to eyeokuri and edit the program you came from. An
    executable Windows won't name keeps it too. With no window in front there is none."""
    if seen is None:
        return None
    if seen.own or seen.shell or not seen.exe:
        return previous
    if previous is not None and previous.key == seen.exe.lower():
        return previous
    known = programs.get(seen.exe.lower())
    if known is not None:
        return known
    return new_program(folder, seen, programs)
