# Stage 1 research notes

Goal: advance a visual novel (send `Enter` / click) using only the eyes, so
the reader keeps control of pacing without touching the keyboard.

This document collects what exists today, what hardware and software we
could build on, which eye gestures are candidates for "next line", and a
recommended path for a first prototype.

## 1. Does a solution already exist?

No ready-made tool was found that targets visual novels specifically.
Related prior work:

| Project / work | What it does | Relevance |
| --- | --- | --- |
| **Text 2.0 / eyeBook** (Biedert et al., DFKI) | Detects *reading* vs. *non-reading* fixations in real time; does gaze-based auto-scroll and page turning, triggers effects as text is read. | Closest concept: "advance when the user has finished reading". Proven with IR trackers. |
| Gaze-based auto-scroll research (several papers, a Microsoft Research study, US patents 9864498 / 10534526) | Scrolls text when gaze reaches the lower part of the screen or reading is detected. | Same idea applied to scrolling; patents worth reading before any commercial use. |
| **Windows Eye Control** | OS-level gaze mouse and keyboard (dwell clicking). | Could already "click" the VN by dwelling, but is clunky for reading and is **not supported on Tobii Eye Tracker 5**. |
| **Google Project Gameface** (open source) | Webcam + MediaPipe face mesh; maps 52 facial gestures (raise eyebrows, open mouth…) and head movement to mouse/keys. | Off-the-shelf way to map a facial gesture to `Enter` today. Not gaze-based, but a good baseline and code reference. |
| **Tobii Game Hub / in-game integrations** | Gaze-aware UI in supported games. | No VN integrations found. |

Conclusion: the idea is novel as a product, but every building block exists.

## 2. Hardware options

| Option | Accuracy | Head movement | Cost | Notes |
| --- | --- | --- | --- | --- |
| Consumer IR tracker (Tobii Eye Tracker 5) | ~0.5–1° | Tolerates normal head motion (also tracks head) | ~US$250 | 133 Hz. SDK is Stream Engine (C/C#); Python bindings exist only as community projects. Licence forbids storing/analysing gaze data without an analytical licence – real-time interaction use is the intended case. |
| Research IR tracker (Tobii Pro, Pupil Labs Core) | ~0.5° | Good | High | Overkill; Pupil Core is open source but head-mounted. |
| Plain webcam + ML gaze model | ~1–4° (WebGazer ≈ 3–4°, newer DL models such as GazeFollower ≈ 1 cm after calibration) | Must be handled in software; accuracy degrades with motion and lighting | Free | Most accessible. Good enough for coarse regions (e.g. "text box" vs. "bottom-right corner"), not for word-level tracking. |

Implication: with a **webcam** we should design gestures that need only
coarse gaze (a few large screen regions) or no gaze position at all
(blinks, eye closure, glance direction). With an **IR tracker**, true
"finished reading this line" detection becomes feasible.

## 3. Software building blocks

Webcam:
- **MediaPipe Face Landmarker** – 478 landmarks incl. iris; runs real-time on CPU. Gives eye openness (Eye Aspect Ratio) for blinks and iris position relative to the eye corners for coarse gaze direction. Head pose can be estimated from the same mesh, which lets us compensate for small head movements.
- **GazeFollower** (Python, pip `gazefollower`) – deep-learning webcam gaze with calibration; ~1.1 cm accuracy reported.
- **EyeTrax** (Python) – webcam gaze with calibration workflows and filtering.
- **GazeTracking** (antoinelame) – simple pupil-position / blink library; older dlib-based approach.
- **WebGazer.js** – browser-based; less relevant for a desktop tool.

IR tracker:
- Tobii Stream Engine (C) with community Python wrappers (`python-tobii-stream-engine`, `PyEyetracker`).

Sending input to the game (Windows, where most VNs run):
- `SendInput` / `pyautogui` / `pynput` for key presses or mouse clicks. Some engines read input differently (DirectInput, focus requirements), so we should test the common engines (KiriKiri, Ren'Py, Unity, Siglus, etc.) and support `Enter`, `Space`, left click and mouse-wheel-down as configurable outputs.
- Optional: text hookers (Textractor, LunaTranslator) can expose the current line's text. Line length lets us estimate expected reading time, which is useful to reject accidental triggers ("you can't have read 80 characters in 300 ms").

## 4. Candidate eye gestures for "next line"

The core problem in gaze interaction is the **Midas touch**: the eyes are
used for looking, so anything you look at may be triggered by accident.
Gesture options, roughly from simplest to most ambitious:

| Gesture | Needs | Pros | Cons |
| --- | --- | --- | --- |
| **Long blink / deliberate eye closure** (e.g. 300–600 ms) | Webcam, EAR only | Very robust, no calibration, head motion barely matters | Normal blinks are 100–400 ms so threshold needs tuning per user; repeated closing is tiring over hours. |
| **Wink (one eye)** | Webcam | Clearly intentional | Not everyone can wink comfortably. |
| **Dwell on a "next" zone** (e.g. bottom-right corner, 400–700 ms) | Coarse gaze | Intuitive, mirrors the VN's "next" arrow | Needs calibration; Midas touch if the zone overlaps text or art. |
| **Glance-out-and-back gesture** (look at a corner then back to text) | Coarse gaze | Saccade-based gestures are insensitive to calibration drift (Drewes & Schmidt 2007) | Slightly unnatural; must learn it. |
| **Implicit: finished reading** (gaze reaches end of last line, then a return sweep / leaves text box) | Accurate gaze (IR) + text box location (+ text length) | Most natural – no gesture at all | Hard with a webcam; readers re-read and look at art; needs a short cancel window. |

Recommendation: start with **long blink** (webcam only) as the baseline
trigger, add **dwell-on-zone** once gaze calibration works, and treat
**implicit end-of-reading** as the research goal for IR-tracker users.
Every trigger should give feedback (sound or small overlay) and have a
cooldown to avoid double-advances.

## 5. Requirements / difficulty

- **Head movement**: must tolerate small movements. Landmark-based approaches normalise by face/eye geometry; IR trackers handle it in hardware. Larger movements need re-calibration or head-pose compensation.
- **Lighting & glasses**: webcam accuracy drops in dim light and with reflective glasses – common when reading in the evening. Should be tested early.
- **Latency**: budget ~100–200 ms from gesture to key press; webcam at 30 fps is enough for blinks and dwell.
- **False positives vs. negatives**: an accidental skip is worse than a missed trigger (you lose a line; VNs usually have backlog, but it's annoying). Prefer conservative thresholds plus a per-user calibration step.
- **CPU**: MediaPipe on CPU is light enough to run alongside a VN.
- **Privacy**: process frames locally; never store video.

Difficulty estimate:
- Blink trigger with webcam: **easy** (a weekend prototype).
- Dwell-zone with webcam gaze: **moderate** (calibration, smoothing, drift).
- Reliable implicit end-of-reading detection: **hard** (research-level; realistic with an IR tracker).

## 6. Suggested next steps (Stage 2 prototype)

1. Python + OpenCV + MediaPipe script that detects a long blink and sends `Enter` to the foreground window, with configurable thresholds and a cooldown.
2. Test with 2–3 popular VN engines to confirm input injection works.
3. Add calibration + coarse gaze (MediaPipe iris or GazeFollower) and a dwell-zone trigger.
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
