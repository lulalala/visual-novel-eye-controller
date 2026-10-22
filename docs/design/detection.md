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

`HeadTracker` in `head.py` reports yaw and pitch relative to the median pose over the last `head.baseline_window_s` seconds (10 by default). An off-center webcam or a habitual slight tilt therefore reads as 0°. Brief turns such as a head shake or nod barely move the median, so it stays close to the resting pose. For the first `head.warmup_s` seconds (2 by default), and again after a face loss longer than the window, the history is too short to trust, so the tracker reports no head pose and head gestures can't start.

Pitch is positive when the head tilts down, because image y grows downward.

## Output kinds

Each gesture's `output` (in `[gestures.NAME]`) is empty, which sends nothing, or one of two kinds:

- Keystroke and mouse outputs, listed in `OUTPUT_NAMES` in `outputs.py`: `enter`, `space`, `left_click`, `right_click`, `wheel_down`, `up`, `down`. `Engine` sends these to the foreground window.
- App-level outputs, which start with `app:`: currently only `app:toggle_pause`. `Engine.step()` handles these itself.
