---
title: Get started
sidebar:
  order: 1
description: Install eyeokuri, let it learn your open eyes, and advance a visual novel with a blink.
---

eyeokuri watches your webcam and sends `Enter` to the game when you blink. Camera frames are processed in memory and never saved or sent anywhere.

## Install

Download `eyeokuri-setup.exe` from the [latest release](https://github.com/lulalala/eyeokuri/releases/latest) and run it. It installs eyeokuri for your Windows account without administrator rights and adds it to the Start menu. The face model is included, so eyeokuri works offline.

Windows might warn about an unknown publisher because the app is not signed. Select **More info**, then **Run anyway**.

Your settings are saved in `%APPDATA%\eyeokuri\config.toml`. Upgrading or uninstalling eyeokuri keeps them.

## Start reading

1. Start eyeokuri and keep your eyes open normally for about 2 seconds. It learns your "eyes open" level and keeps adapting as your posture changes.
2. Switch to your game.
3. Blink to advance the text.

## Default gestures

- **Blink** (both eyes closed for at least 0.1 s): sends `Enter` when you reopen your eyes. Closing your eyes for more than 1 s cancels the blink.
- **Shake your head** to pause or resume: turn past about 15° to one side, then past about 15° to the other side, within 1.5 s.
- **Nod up or down** sends the `up` or `down` arrow key. It is off by default. You can turn it on with its checkbox in the main window.
- **Tilt your head toward your right shoulder** (`tilt_right`) past about 15° for 0.3 s to hold down `ctrl`, which skips text in many games. `ctrl` comes up when you straighten up. If you hold the tilt for more than about 10 s, eyeokuri takes it as your usual pose and lets go.
- **Tilt your head toward your left shoulder** (`tilt_left`) is off by default and sends nothing until you choose a key with its button in the main window.
- **Wink with your left or right eye** (`wink_left`, `wink_right`) is off by default and sends nothing until you choose a key with its button in the main window. A wink counts when one eye is at least 0.25 less open than the other, then both are level again 0.05–0.6 s later. A normal blink closes both eyes, so it doesn't count as a wink. Turning your head makes one eye look narrower to the camera, so winks count only with your head within 20° sideways and 10° up or down. Run the [wizard](../gesture-wizard/) to fit it to your face.

A shake often comes with a blink, so it can also advance one line.

## Blink freely or on purpose

By default, any closure of both eyes lasting 0.1–1 s counts, so a natural blink advances the text. If you'd rather blink freely and close your eyes on purpose to advance, raise the blink's minimum closed time to about 0.35–0.45 s in its [gesture window](../edit-a-gesture/), or run the [wizard](../gesture-wizard/) with a deliberate blink. Ordinary blinks lasted 0.17–0.34 s in our first test.

## If the game doesn't respond

eyeokuri sends keys with hardware scan codes, so DirectInput games receive them too. If the game runs as administrator, run eyeokuri as administrator as well, or Windows blocks the input.

## Next steps

Learn the [main window](../main-window/), then [edit a gesture](../edit-a-gesture/) or [set it up with the wizard](../gesture-wizard/). To change gestures in the config file, see [Edit gestures in the config file](../config-file/).
