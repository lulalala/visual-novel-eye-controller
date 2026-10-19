# Stage 1 research notes

Goal: let a visual novel reader advance the text (`Enter` / click) using only eye gestures, without touching the keyboard.

This page covers prior art, hardware and software options, gesture candidates, and a recommended path for Stage 2.

## Prior art

No ready-made tool targets visual novels specifically. Related prior work:

| Project / work | What it does | Relevance |
| --- | --- | --- |
| **Text 2.0 / eyeBook** (Biedert et al., DFKI) | Detects *reading* vs. *non-reading* fixations in real time; does gaze-based auto-scroll and page turning, triggers effects as text is read. | Closest concept: "advance when the user has finished reading". Proven with IR trackers. |
| Gaze-based auto-scroll research (several papers, a Microsoft Research study, US patents 9864498 / 10534526) | Scrolls text when gaze reaches the lower part of the screen or reading is detected. | Same idea applied to scrolling; patents worth reading before any commercial use. |
| **Windows Eye Control** | OS-level gaze mouse and keyboard (dwell clicking). | Can already "click" the VN by dwelling, but is clunky for reading and is **not supported on Tobii Eye Tracker 5**. |
| **Google Project Gameface** (open source) | Webcam + MediaPipe face mesh; maps 52 facial gestures (raise eyebrows, open mouth…) and head movement to mouse/keys. | Off-the-shelf way to map a facial gesture to `Enter` today. Not gaze-based, but a good baseline and code reference. |
| **Tobii Game Hub / in-game integrations** | Gaze-aware UI in supported games. | No VN integrations found. |

The idea is novel as a product, but every building block exists.

## Hardware options

| Option | Accuracy | Head movement | Cost | Notes |
| --- | --- | --- | --- | --- |
| Consumer IR tracker (Tobii Eye Tracker 5) | ~0.5–1° | Tolerates normal head motion (also tracks head) | ~US$250 | 133 Hz. SDK is Stream Engine (C/C#); Python bindings exist only as community projects. License forbids storing/analyzing gaze data without an analytical license – real-time interaction use is the intended case. |
| Research IR tracker (Tobii Pro, Pupil Labs Core) | ~0.5° | Good | High | Overkill; Pupil Core is open source but head-mounted. |
| Plain webcam + ML gaze model | ~1–4° (WebGazer ≈ 3–4°, newer DL models such as GazeFollower ≈ 1 cm after calibration) | Must be handled in software; accuracy degrades with motion and lighting | Free | Most accessible. Good enough for coarse regions (e.g. "text box" vs. "bottom-right corner"), not for word-level tracking. |

With a **webcam**, design gestures that need only coarse gaze (a few large screen regions) or no gaze position at all (blinks, eye closure, glance direction). With an **IR tracker**, true "finished reading this line" detection becomes feasible.

### Minimum webcam spec for the blink prototype

Testing so far covers only the MacBook built-in camera, where it works well. The figures below come from what the code needs, not from testing desktop webcams. `eyeokuri` requests 640×480 at 30 fps. MediaPipe works on a small face crop, so higher resolution adds little. Frame rate, exposure, and placement matter more.

| | Minimum | Recommended | Why |
| --- | --- | --- | --- |
| Frame rate | 15 fps, actually delivered | 30 fps | Blink length is timed between frames: a 0.15 s blink is ~2 frames at 15 fps vs ~4–5 at 30 fps. Below 15 fps, short blinks get missed or measured wrong. |
| Resolution | 640×480 | 720p | Each eye needs roughly 25+ px width. 1080p/4K only costs CPU. |
| Field of view | Any (~60–90°) | ~65–78° | Wide angle makes the face small. Sit closer if the face fills less than about a quarter of the frame width. |
| Low light | — | Holds 30 fps indoors | The usual failure: cheap cameras drop to 10–15 fps in dim rooms to get more exposure. |
| Connection | USB 2.0, UVC (driver-free) | — | Standard UVC works with OpenCV on Windows and macOS. |

Any 720p/30fps UVC webcam (Logitech C270/C920 class) should work, as long as it holds 30 fps in the room's lighting. No 1080p, 60 fps, IR, or depth needed.

Setup matters more than the camera:
- Light the face from the front (lamp or monitor). A window behind the user hurts.
- Mount the camera on top of the monitor, centered. If it is off to the side, the head looks turned: blinks are ignored beyond 12° of turn, and head-shake detection gets less reliable.
- Glare on glasses can hide the eyelids. Tilt the camera or lamp a little.
- Turn off driver "low-light compensation" or auto-exposure modes that lower fps.

To check a camera, run `eyeokuri --preview` and press `p` to pause, so gestures print instead of sending keys. The preview shows live fps. It should stay near 30. Blink normally for a minute: if ordinary blinks are logged as "too short", or fps drops below about 20, improve the lighting or try another camera. Select a non-default camera with `--set camera.index=1`.

## Software building blocks

Webcam:
- **MediaPipe Face Landmarker** – 478 landmarks incl. iris; runs real-time on CPU. Gives eye openness (Eye Aspect Ratio) for blinks and iris position relative to the eye corners for coarse gaze direction. Head pose can be estimated from the same mesh, which allows head-movement compensation.
- **EyeTrax** (Python) – webcam gaze with calibration workflows and filtering.
- **GazeTracking** (antoinelame) – simple pupil-position / blink library; older dlib-based approach.
- **WebGazer.js** – browser-based; less relevant for a desktop tool.

IR tracker:
- Tobii Stream Engine (C) with community Python wrappers (`python-tobii-stream-engine`, `PyEyetracker`).

Sending input to the game (Windows, where most VNs run):
- `SendInput` / `pyautogui` / `pynput` for key presses or mouse clicks. Some engines read input differently (DirectInput, focus requirements), so test the common engines (KiriKiri, Ren'Py, Unity, Siglus, etc.) and support `Enter`, `Space`, left click, and mouse-wheel-down as configurable outputs.
- Optional: text hookers (Textractor, LunaTranslator) can expose the current line's text. Line length allows estimation of expected reading time, which helps reject accidental triggers ("you can't have read 80 characters in 300 ms").

## Eye gesture candidates

The core problem in gaze interaction is the **Midas touch**: the eyes are used for looking, so anything you look at may be triggered accidentally. Gesture options, roughly from simplest to most ambitious:

| Gesture | Needs | Pros | Cons |
| --- | --- | --- | --- |
| **Deliberate eye closure** (e.g. 300–600 ms) | Webcam, EAR only | Very robust, no calibration, head motion barely matters | Normal blinks are 100–400 ms so threshold needs tuning per user; repeated closing is tiring over hours. |
| **Wink (one eye)** | Webcam | Clearly intentional | Not everyone can wink comfortably. |
| **Dwell on a "next" zone** (e.g. bottom-right corner, 400–700 ms) | Coarse gaze | Intuitive, mirrors the VN's "next" arrow | Needs calibration; Midas touch if the zone overlaps text or art. |
| **Glance-out-and-back gesture** (look at a corner then back to text) | Coarse gaze | Saccade-based gestures are insensitive to calibration drift (Drewes & Schmidt 2007) | Slightly unnatural; must learn it. |
| **Implicit: finished reading** (gaze reaches end of last line, then a return sweep / leaves text box) | Accurate gaze (IR) + text box location (+ text length) | Most natural – no gesture at all | Hard with a webcam; readers re-read and look at art; needs a short cancel window. |

Recommendation: start with **deliberate eye closure** (webcam only) as the baseline trigger, add **dwell-on-zone** once gaze calibration works, and treat **implicit end-of-reading** as the research goal for IR-tracker users. Every trigger should give feedback (sound or small overlay) and have a cooldown to avoid double-advances.

## Requirements and difficulty

- **Head movement**: must tolerate small movements. Landmark-based approaches normalize by face/eye geometry; IR trackers handle it in hardware. Larger movements need re-calibration or head-pose compensation.
- **Lighting and glasses**: webcam accuracy drops in dim light and with reflective glasses — common when reading in the evening. Test this early.
- **Latency**: budget ~100–200 ms from gesture to key press; webcam at 30 fps is enough for blinks and dwell.
- **False positives vs. negatives**: an accidental skip is worse than a missed trigger (you lose a line; VNs usually have a backlog, but it is annoying). Prefer conservative thresholds plus a per-user calibration step.
- **CPU**: MediaPipe on CPU is light enough to run alongside a VN.
- **Privacy**: process frames locally; never store video.

Difficulty estimate:
- Blink trigger with webcam: **easy** (a weekend prototype).
- Dwell-zone with webcam gaze: **moderate** (calibration, smoothing, drift).
- Reliable implicit end-of-reading detection: **hard** (research-level; realistic with an IR tracker).

## Library licenses

Checked October 2026 (PyPI metadata, project LICENSE files, vendor terms).
Verify again before release, as licenses can change between versions.

| Library | Purpose | License | OK to use in an open-source project? |
| --- | --- | --- | --- |
| MediaPipe (incl. Face Landmarker model) | Face/iris landmarks, blinks | Apache-2.0 | Yes – permissive |
| OpenCV (`opencv-python`) | Camera capture, image processing | Apache-2.0 | Yes |
| NumPy | Maths | BSD-3-Clause (+ other permissive) | Yes |
| dlib | Older face landmark approach | Boost Software License | Yes |
| EyeTrax | Webcam gaze + calibration | MIT | Yes |
| GazeTracking (antoinelame) | Pupil position / blink | MIT | Yes |
| Project Gameface (google) | Reference code for gesture → input | Apache-2.0 (repo archived Sep 2025) | Yes, but unmaintained |
| **GazeFollower** | Deep-learning webcam gaze | **CC BY-NC-SA 4.0** | Only non-commercially, and derivatives must keep the same license; it cannot be bundled into an MIT/Apache project without imposing these terms |
| **WebGazer.js** | Browser webcam gaze | **GPL-3.0** (LGPL-3.0 option for small companies) | Copyleft – using it makes the combined work GPL |
| pyautogui | Send key/mouse input | BSD-3-Clause | Yes |
| keyboard (boppreh) | Send key input | MIT | Yes |
| pynput | Send key/mouse input | LGPL-3.0 | Yes as an unmodified dependency; modifications to pynput itself must be shared |
| Textractor / LunaTranslator | Hook current VN line text | GPL-3.0 | Use as a separate program (e.g. read its output) rather than linking/bundling, unless you go GPL |
| **Tobii Stream Engine** (Eye Tracker 5) | IR tracker access | **Proprietary** (Tobii SDK license) | Usable for "Interactive Use" only: gaze as live input is allowed, but storing/analyzing gaze data or exposing it via an API is not. Cannot be redistributed in this repo; users install Tobii's runtime themselves |
| tobii-research (Tobii Pro SDK) | Pro tracker access | Proprietary | Pro hardware only |
| python-tobii-stream-engine, PyEyetracker | Community Python wrappers | No clear license found | Treat as "all rights reserved" until a license is confirmed; writing a small ctypes wrapper is the safer path |

Takeaways:
- A permissive stack is available: **MediaPipe + OpenCV + EyeTrax/own code + pyautogui or keyboard** are all Apache/MIT/BSD.
- Avoid GazeFollower due to license for now.
- Tobii support must stay an optional backend that loads the user's installed runtime and never logs gaze data.
- This repo has no LICENSE file yet. With the stack above, MIT or Apache-2.0 would be compatible.

## Next steps for Stage 2

1. Python + OpenCV + MediaPipe script that detects a blink and sends `Enter` to the foreground window, with configurable thresholds and a cooldown.
2. Test with 2–3 popular VN engines to confirm input injection works.
3. Add calibration + coarse gaze behind a pluggable backend interface (MediaPipe/EyeTrax first), benchmark them on the same 9-point test, and add a dwell-zone trigger.
4. Optional backend for Tobii IR trackers; experiment with end-of-reading detection.

## Sources

- Text 2.0 framework: https://www.researchgate.net/publication/254003473_The_text_20_framework_writing_web-based_gaze-controlled_realtime_applications_quickly_and_easily
- Reading with gaze-based auto-scrolling: https://www.researchgate.net/publication/262238749_Reading_on-screen_text_with_gaze-based_auto-scrolling
- Gaze and scrolling strategies (Microsoft Research): https://www.microsoft.com/en-us/research/wp-content/uploads/2016/07/PETMEI2015scrolling_petmei_15_final.pdf
- Patent "Automatic scrolling based on gaze detection": https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9864498
- Drewes & Schmidt, Interacting with the Computer using Gaze Gestures: https://www.medien.ifi.lmu.de/pubdb/publications/pub/drewes2007interact/drewes2007interact.pdf
- Gaze gestures or dwell-based interaction?: https://www.researchgate.net/publication/254007866_Gaze_gestures_or_dwell-based_interaction
- Webcam vs in-lab eye tracking: https://pmc.ncbi.nlm.nih.gov/articles/PMC11627531/
- WebGazer: https://cs.brown.edu/people/apapouts/papers/ijcai2016webgazer.pdf
- GazeFollower: https://github.com/GanchengZhu/GazeFollower
- EyeTrax: https://github.com/ck-zhang/eyetrax
- GazeTracking: https://github.com/antoinelame/GazeTracking
- MediaPipe EAR blink detection example: https://github.com/Pushtogithub23/Eye-Blink-Detection-using-MediaPipe-and-OpenCV
- Project Gameface: https://blog.google/innovation-and-ai/products/google-project-gameface/
- Tobii Eye Tracker 5 not compatible with Windows Eye Control: https://help.tobii.com/hc/en-us/articles/360014744577-Eye-Tracker-5-is-not-compatible-with-Eye-Control
- Windows Eye Control: https://support.microsoft.com/en-us/windows/get-started-with-eye-control-in-windows-1a170a20-1083-2452-8f42-17a7d4fe89a9
- Python Tobii Stream Engine bindings: https://github.com/betaboon/python-tobii-stream-engine
- Return sweeps in reading: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6863793/
- GazeFollower license (CC BY-NC-SA 4.0) and model availability: https://pypi.org/project/gazefollower/
- GazeFollower paper (ACM PACMCGIT 2025): https://doi.org/10.1145/3729410 , https://www.researchgate.net/publication/391149662_GazeFollower_An_open-source_system_for_deep_learning-based_gaze_tracking_with_web_cameras
- EyeTrax: https://pypi.org/project/eyetrax/
- GazeTracking license: https://github.com/antoinelame/GazeTracking/blob/master/LICENSE
- WebGazer license: https://github.com/brownhci/WebGazer/blob/master/LICENSE.md
- Project Gameface license: https://github.com/google/project-gameface/blob/main/LICENSE
- MediaPipe Face Mesh V2 model card: https://storage.googleapis.com/mediapipe-assets/Model%20Card%20MediaPipe%20Face%20Mesh%20V2.pdf
- Tobii SDK license agreement: https://www.tobii.com/products/integration/tobii-sdk-license
- Tobii Core/Gaming SDK license (Interactive vs Analytical use): https://developer.tobii.com/license-agreement/
- Textractor: https://github.com/Artikash/Textractor
- PyPI metadata for mediapipe, opencv-python, eyetrax, pynput, pyautogui, keyboard, dlib, numpy, tobii-research: https://pypi.org/
