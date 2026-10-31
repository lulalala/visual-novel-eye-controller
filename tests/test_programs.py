from dataclasses import replace
from pathlib import Path

import pytest

from eyeokuri.config import Config, GestureConfig, StepConfig, apply_overrides
from eyeokuri.foreground import Seen
from eyeokuri.programs import (
    BASE, PROGRAM, Program, dump_program, file_name, load_program, load_programs, merged, new_program,
    next_target, split,
)


FOLDER = Path("configs")


def clannad(**fields):
    return Program(**{"exe": "CLANNAD.exe", "name": "CLANNAD", "path": FOLDER / "clannad.toml", **fields})


def with_blink_key(config, key):
    return apply_overrides(config, {"gestures": {"blink": {"output": key}}})


def test_a_gesture_edit_in_the_program_tab_stores_only_the_difference():
    base = Config()
    _, program = split(base, clannad(), PROGRAM, with_blink_key(base, "space"))
    assert program.overrides == {"blink": {"output": "space"}}


def test_a_program_config_applies_over_the_base():
    program = clannad(overrides={"blink": {"output": "space"}})
    config = merged(Config(), program)
    assert config.gestures["blink"].output == "space"
    assert config.gestures["blink"].steps == Config().gestures["blink"].steps


def test_a_base_change_reaches_a_program_that_doesnt_override_it():
    program = clannad(overrides={"blink": {"output": "space"}})
    base = apply_overrides(Config(), {"gestures": {"nod_up": {"output": "page_up"}, "blink": {"output": "f5"}}})
    config = merged(base, program)
    assert config.gestures["nod_up"].output == "page_up"
    assert config.gestures["blink"].output == "space"


def test_non_gesture_edits_in_the_program_tab_go_to_the_base():
    base, program = Config(), clannad()
    edited = replace(merged(base, program), app=replace(base.app, paused=True))
    new_base, new_program = split(base, program, PROGRAM, edited)
    assert new_base.app.paused
    assert new_program.overrides == {}


def test_edits_in_the_base_tab_leave_the_program_alone():
    program = clannad(overrides={"blink": {"output": "space"}})
    base, same = split(Config(), program, BASE, with_blink_key(Config(), "f5"))
    assert base.gestures["blink"].output == "f5"
    assert same is program


def test_a_program_only_gesture_is_written_with_its_steps_and_reads_back(tmp_path):
    base = Config()
    mine = GestureConfig(steps=[StepConfig(signal="eyes", below_ratio=0.5)], output="space")
    edited = replace(base, gestures={**with_blink_key(base, "f5").gestures, "mine": mine})
    _, program = split(base, clannad(path=tmp_path / "clannad.toml"), PROGRAM, edited)
    text = dump_program(base, program)
    assert "[gestures.mine]\nsteps = [" in text
    program.path.write_text(text, encoding="utf-8")
    assert merged(base, load_program(program.path)) == edited


def test_the_file_names_the_program_and_reads_back(tmp_path):
    program = clannad(path=tmp_path / "clannad.toml", overrides={"blink": {"output": "space"}})
    text = dump_program(Config(), program)
    assert text == ('version = 1\n\n[program]\nexe = "CLANNAD.exe"\nname = "CLANNAD"\n\n'
                    '[gestures.blink]\noutput = "space"\n')
    program.path.write_text(text, encoding="utf-8")
    assert load_program(program.path) == replace(program, saved=True)


def test_a_program_file_can_only_change_gestures(tmp_path):
    path = tmp_path / "x.toml"
    path.write_text('version = 1\n[program]\nexe = "x.exe"\n[camera]\nindex = 1\n', encoding="utf-8")
    with pytest.raises(ValueError, match="only \\[program\\] and \\[gestures.NAME\\]"):
        load_program(path)


def test_a_program_file_needs_its_exe(tmp_path):
    path = tmp_path / "x.toml"
    path.write_text("version = 1\n[gestures.blink]\noutput = \"space\"\n", encoding="utf-8")
    with pytest.raises(ValueError, match="needs a \\[program\\] section"):
        load_program(path)


def test_an_override_of_a_gesture_the_base_lost_is_ignored_and_logged(tmp_path):
    (tmp_path / "clannad.toml").write_text(
        'version = 1\n[program]\nexe = "CLANNAD.exe"\n[gestures.gone]\noutput = "space"\n', encoding="utf-8")
    logs = []
    programs = load_programs(tmp_path, Config(), logs.append)
    assert "gone" not in merged(Config(), programs["clannad.exe"]).gestures
    assert logs == [f"gestures.gone in {tmp_path / 'clannad.toml'}: not in the base config, ignored"]


def test_a_bad_program_file_is_skipped_and_the_others_load(tmp_path):
    (tmp_path / "bad.toml").write_text('version = 1\n[program]\nexe = "bad.exe"\n[gestures.blink]\noutput = "nope"\n',
                                       encoding="utf-8")
    (tmp_path / "good.toml").write_text('version = 1\n[program]\nexe = "good.exe"\n', encoding="utf-8")
    logs = []
    programs = load_programs(tmp_path, Config(), logs.append)
    assert list(programs) == ["good.exe"]
    assert logs[0].startswith(f"Ignored {tmp_path / 'bad.toml'}: gestures.blink.output")


def test_no_folder_means_no_programs(tmp_path):
    assert load_programs(tmp_path / "missing", Config(), print) == {}


def test_the_file_name_comes_from_the_exe():
    assert file_name("CLANNAD.exe") == "clannad.toml"
    assert file_name("Little Busters!.EXE") == "little_busters_.toml"


def test_a_new_program_gets_a_file_name_no_other_program_uses():
    taken = {"clannad.exe": replace(clannad(exe="Clannad_Other.exe"), saved=True)}
    program = new_program(FOLDER, Seen("CLANNAD.exe", "CLANNAD"), taken)
    assert program.path == FOLDER / "clannad-2.toml"


def test_a_known_exe_selects_its_program_whatever_the_case():
    program = replace(clannad(), saved=True)
    assert next_target(None, Seen("clannad.EXE", "Chapter 3"), {"clannad.exe": program}, FOLDER) is program


def test_an_unknown_exe_offers_to_create_a_config_named_after_the_window():
    target = next_target(None, Seen("notepad.exe", "notes.txt - Notepad"), {}, FOLDER)
    assert (target.exe, target.name, target.saved) == ("notepad.exe", "notes.txt - Notepad", False)


def test_eyeokuri_and_the_shell_keep_the_previous_program():
    previous = replace(clannad(), saved=True)
    for seen in (Seen("eyeokuri.exe", "eyeokuri", own=True), Seen("explorer.exe", "", shell=True),
                 Seen("", "Elevated")):
        assert next_target(previous, seen, {}, FOLDER) is previous


def test_no_window_in_front_means_no_program():
    assert next_target(replace(clannad(), saved=True), None, {}, FOLDER) is None


def test_the_same_program_in_front_keeps_its_working_copy():
    previous = clannad(overrides={"blink": {"output": "space"}})
    assert next_target(previous, Seen("CLANNAD.exe", "Other title"), {}, FOLDER) is previous
