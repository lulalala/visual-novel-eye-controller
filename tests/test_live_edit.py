from dataclasses import replace

from eyeokuri.config import Config, apply_overrides
from eyeokuri.gui.live_edit import APPLY_DELAY_MS, LiveEdit


class FakeWin:
    """Runs after() callbacks only when run() is called."""

    def __init__(self):
        self.pending = {}
        self._next = 0

    def after(self, ms, callback):
        self._next += 1
        self.pending[str(self._next)] = (ms, callback)
        return str(self._next)

    def after_cancel(self, after_id):
        # Like Tk, canceling one that already ran does nothing.
        self.pending.pop(after_id, None)

    def run(self):
        pending, self.pending = self.pending, {}
        for _ms, callback in pending.values():
            callback()


class FakeWidget:
    def __init__(self):
        self.options = {}

    def configure(self, **options):
        self.options.update(options)


class FakeApp:
    def __init__(self, config, fail_save=False):
        self.config = config
        self.applied = []
        self.saved = []
        self._fail_save = fail_save

    def apply_config(self, config):
        self.config = config
        self.applied.append(config)

    def save_config(self, config):
        if self._fail_save:
            raise OSError("disk full")
        self.apply_config(config)
        self.saved.append(config)


def make(edited, fail_save=False):
    app, win, message, ok = FakeApp(Config(), fail_save), FakeWin(), FakeWidget(), FakeWidget()
    return LiveEdit(app, win, message, ok, edited), app, win, message, ok


def quiet():
    return replace(Config(), feedback=replace(Config().feedback, sound=False))


def test_valid_edits_apply_once_they_stop_changing():
    edit, app, win, message, ok = make(quiet)
    assert edit.refresh() == quiet()
    assert (message.options["text"], ok.options["state"]) == ("", "normal")
    assert [ms for ms, _ in win.pending.values()] == [APPLY_DELAY_MS]
    assert app.applied == []
    win.run()
    assert app.applied == [quiet()]


def test_another_edit_restarts_the_wait():
    edit, app, win, *_ = make(quiet)
    edit.refresh()
    edit.refresh()
    assert len(win.pending) == 1


def test_invalid_edits_show_why_and_turn_off_ok():
    bad = apply_overrides(Config(), {"gestures": {"blink": {"output": "nonsense"}}})
    edit, app, win, message, ok = make(lambda: bad)
    assert edit.refresh() is None
    assert "gestures.blink.output" in message.options["text"]
    assert ok.options["state"] == "disabled"
    assert win.pending == {}


def test_a_field_error_wins_over_the_settings():
    edit, app, win, message, ok = make(quiet)
    edit.errors["camera.fps"] = "Not a whole number: camera.fps = 'x'"
    assert edit.refresh() is None
    assert message.options["text"] == "Not a whole number: camera.fps = 'x'"


def test_save_writes_the_edits_or_shows_why_it_couldnt():
    edit, app, *_ = make(quiet)
    assert edit.save() == quiet()
    assert app.saved == [quiet()]
    edit, app, _win, message, _ok = make(quiet, fail_save=True)
    assert edit.save() is None
    assert message.options["text"] == "disk full"


def test_revert_goes_back_to_the_settings_in_use_when_opened():
    edit, app, win, *_ = make(quiet)
    edit.revert()
    assert app.applied == []
    edit.refresh()
    win.run()
    edit.revert()
    assert app.config == Config()


def test_closing_without_changes_doesnt_ask():
    edit, *_ = make(Config)
    assert edit.may_discard("title")


def test_close_cancels_a_pending_apply():
    edit, app, win, *_ = make(quiet)
    edit.refresh()
    edit.close()
    assert win.pending == {}
