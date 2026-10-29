import threading
import time

from eyeokuri.outputs import HeldKeys, KeyRepeater


def test_shared_key_goes_down_with_the_first_output_and_up_with_the_last():
    held = HeldKeys()
    assert held.press(["ctrl"]) == ["ctrl"]
    assert held.press(["ctrl"]) == []
    assert held.release(["ctrl"]) == []
    assert held.release(["ctrl"]) == ["ctrl"]


def test_combination_presses_and_releases_only_the_keys_no_one_else_holds():
    held = HeldKeys()
    held.press(["ctrl"])
    assert held.press(["ctrl", "s"]) == ["s"]
    assert held.release(["s", "ctrl"]) == ["s"]
    assert held.release(["ctrl"]) == ["ctrl"]


def test_releasing_a_key_that_is_up_sends_nothing():
    held = HeldKeys()
    assert held.release(["enter"]) == []
    assert held.press(["enter"]) == ["enter"]


def counting():
    count = []
    lock = threading.Lock()

    def press():
        with lock:
            count.append(time.monotonic())

    return count, press


def test_repeater_presses_again_and_again_after_its_delay():
    count, press = counting()
    repeater = KeyRepeater(press, delay_s=0.05, interval_s=0.01)
    time.sleep(0.02)
    assert count == []
    time.sleep(0.2)
    repeater.stop()
    assert len(count) >= 3


def test_no_press_comes_after_stop():
    count, press = counting()
    repeater = KeyRepeater(press, delay_s=0.0, interval_s=0.001)
    time.sleep(0.02)
    repeater.stop()
    stopped = len(count)
    time.sleep(0.03)
    assert len(count) == stopped


def test_key_released_before_the_delay_never_repeats():
    count, press = counting()
    KeyRepeater(press, delay_s=0.2, interval_s=0.01).stop()
    time.sleep(0.05)
    assert count == []
