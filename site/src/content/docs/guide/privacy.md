---
title: Privacy policy
sidebar:
  order: 98
description: What data eyeokuri collects (none), what stays on your PC, and the one network request it can make.
---

eyeokuri does not collect, store or transmit personal data. Everything it does happens on your PC.

## Camera images

eyeokuri reads your webcam to detect blinks and head movements. Each frame is processed in memory and discarded. eyeokuri never writes camera frames to disk and never sends them anywhere.

## What stays on your PC

- **Settings.** eyeokuri saves your settings in `%APPDATA%\eyeokuri\config.toml`. Delete the file to reset them, or uninstall and remove the folder.
- **Log file.** Only if you start eyeokuri with `--log`, it writes numbers (eye openness and head angles per frame) to the file you name. The file contains no images and no identifying information. You decide whether to keep or share it.
- **Key and mouse output.** eyeokuri sends the input you configured, `Enter` by default, to the foreground window. It does not read what you type or what the game shows.

## Network access

The Windows installer includes the face model, so the installed app makes no network requests. When you run eyeokuri from source, the first run downloads the face model from [Google's model storage](https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task). That request is the only network access eyeokuri makes, and it sends no data about you beyond what any download exposes, such as your IP address.

eyeokuri has no analytics, telemetry, crash reporting, accounts or advertising. It does not use the `mediapipe` package, which includes telemetry.

## Third parties

eyeokuri shares no data with third parties. The [third-party software](/eyeokuri/guide/third-party/) it includes runs locally.

## Changes to this policy

If a future version changes how eyeokuri handles data, this page and the release notes will say so. The source code is [open](https://github.com/lulalala/eyeokuri), so you can verify these statements.

## Contact

Report privacy questions or concerns as an [issue on GitHub](https://github.com/lulalala/eyeokuri/issues).
