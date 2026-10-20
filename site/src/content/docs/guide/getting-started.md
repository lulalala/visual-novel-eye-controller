---
title: Get started
description: Install eyeokuri, let it learn your open eyes, and advance a visual novel with a blink.
---

eyeokuri watches your webcam and sends `Enter` to the game when you blink. Camera frames are processed in memory and never saved or sent anywhere.

## Install

Download the Windows build from the [latest release](https://github.com/lulalala/visual-novel-eye-controller/releases/latest). The first run downloads a face model of about 4 MB, so you must be online once.

Windows might warn about an unknown publisher because the app is not signed. Select **More info**, then **Run anyway**.

## Start reading

1. Start eyeokuri and keep your eyes open normally for about 2 seconds. It learns your "eyes open" level and keeps adapting as your posture changes.
2. Switch to your game.
3. Blink to advance the text.

## Default gestures

- **Blink** (both eyes closed for at least 0.15 s): sends `Enter` when you reopen your eyes. Closing your eyes for more than 2 s cancels the blink.
- **Shake your head** to pause or resume: turn past about 15° to one side, then past about 15° to the other side, within 1 s.
- **Nod up or down** sends the `up` or `down` arrow key. It is off by default. You can turn it on in the settings window.

For the gesture wizard and the settings window, see the [README](https://github.com/lulalala/visual-novel-eye-controller#readme).
