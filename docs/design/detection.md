# Eye and head detection

This page explains how `eyeokuri` turns raw eye openness and head pose into the open/closed state and head angles that triggers see. It covers the `[eyes]` and `[head]` config sections. For the overall pipeline, see `sources.md`.

## Eye openness baseline

`EyeStateTracker` in `eyes.py` compares each frame's eye openness with a rolling "eyes open" baseline instead of a fixed threshold. The baseline is the median of the open-eye values from the last `eyes.baseline_window_s` seconds (10 by default). Blinks take up a small fraction of the time, so the median stays near the open-eye level and still follows slow changes in face, camera angle, and posture.

Only frames where the eyes count as open go into the history, so a long closure doesn't drag the baseline down.

The tracker reports `ready` only after the history spans at least `eyes.warmup_s` seconds (2 by default) and holds at least 10 samples. Until then, the eyes always count as open. If the eyes stay "closed" for longer than the baseline window, the history empties and the tracker starts learning again. This recovers from a large posture change that looks like a permanent closure.

## Closed and open thresholds

The eyes count as closed when openness drops below `baseline * close_ratio`, and as open again when it rises above `baseline * open_ratio`. The defaults are `0.55` and `0.75`. This closed state decides which frames the baseline learns from and what the preview shows. Gestures don't use it: their `eyes` steps compare `openness / baseline` with their own `above_ratio`/`below_ratio`.

The two thresholds form a hysteresis band. With a single threshold, noise around it would flip the state on alternate frames. For this reason `close_ratio` must be above 0 and below `open_ratio`; the constructor raises `ValueError` otherwise.

## Combining both eyes

With `eyes.require_both_eyes = true` (the default), the tracker uses the more open of the two eyes, so both must close to count as closed. A wink or a one-eyed squint doesn't trigger. With `false`, it uses the less open eye, so either eye closing counts.

The `wink` signal compares the two eyes instead: right openness over its median minus left openness over its median, taken over the same open-eye history as the baseline. Dividing each eye by its own median keeps the value near 0 when your eyes differ in size, and a two-eye blink also stays near 0 because both eyes drop together. It doesn't depend on `require_both_eyes`. It is `None` until the baseline is ready.

## Head pose baseline

`HeadTracker` in `head.py` reports yaw, pitch and roll relative to the median pose over the last `head.baseline_window_s` seconds (10 by default). An off-center webcam or a habitual slight tilt therefore reads as 0°. Brief turns such as a head shake or nod barely move the median, so it stays close to the resting pose. For the first `head.warmup_s` seconds (2 by default), and again after a face loss longer than the window, the history is too short to trust, so the tracker reports no head pose and head gestures can't start.

Roll samples more than 8° from the median aren't added to the history. Holding a sideways tilt (to keep `ctrl` down with `tilt_right`) would otherwise become the median after about half the window, and the roll would fall back to 0 with the head still tilted. A tilt held past the window empties the history, so the tracker reports no roll for `head.warmup_s` and then learns the new pose.

Pitch is positive when the head tilts down, because image y grows downward. Roll is positive when the top of the head moves toward the image's right, which is the subject's left shoulder.

## Output kinds

Each gesture's `output` (in `[gestures.NAME]`) is empty, which sends nothing, or one of two kinds:

- Keystroke and mouse outputs, listed in `OUTPUT_NAMES` in `outputs.py`: `enter`, `space`, `mouse_left_click`, `mouse_right_click`, `mouse_wheel_down`, `up`, `down`. `Engine` sends these to the foreground window.
- App-level outputs, listed in `APP_OUTPUTS` and named with an `app_` prefix: currently only `app_pause_toggle`. `Engine.step()` handles these itself.

`output_mode` says how a keystroke or mouse output is sent: `press` sends it once, `toggle` holds it down (`Output.down()`) until the gesture fires again (`Output.up()`), and `while` holds it down until the gesture ends.

Every gesture that fires also ends: its trigger returns a `TriggerEvent` with `ended=True` on the frame the signal leaves the box of the step that completed it. If that step is another gesture, it ends when that gesture ends; losing the face or a guard ends it too. Only `while` acts on the end; for the other modes it's the signal moving on. A held output is down for every app, so `Engine` also lets go of it on pause, suspend, new settings, face loss and `close()`. `Engine` tracks each gesture's hold separately, and the `Output` counts who holds each key (`HeldKeys`), so gestures can share keys: a key goes down with the first output that presses it and up with the last that lets go.

While a key is held, the output repeats its key-down after 0.25 s and then every 0.033 s (`KeyRepeater`), like a keyboard's auto-repeat, because some games skip one line per key-down instead of checking whether ctrl is down. Only the last key of a combination repeats, and mouse buttons don't.
