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

Next, learn the [main window](../main-window/), then [edit a gesture](../edit-a-gesture/) or [set it up with the wizard](../gesture-wizard/).
