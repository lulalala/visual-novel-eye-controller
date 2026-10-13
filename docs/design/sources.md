# Signal sources and plugins

Status: step 1 of the [migration plan](#migration-plan) is implemented. Step 2 (plugin loading) is deferred (see [Priority](#priority)).

This document describes how `vn-eye` separates *sensing* (camera, face model, eye tracker) from *recognizing gestures*, and how a third party can add a new sensing method as a separate pip package without changing `vn-eye` itself.

## Priority

The users `vn-eye` most needs to reach are less technical Windows users, many of them with iPhones. They install apps, not pip packages, so a plugin system doesn't help them directly. What they need first is an installer, a simple GUI, and a camera picker that shows camera names.

For that reason, only step 1 of the migration plan was scheduled:

- **Step 1 (done):** the `Source` and `Signals` refactor, with one built-in source, `OpenCVSource`. It removes the leaks listed below whether or not plugins ever exist, and it is what any future built-in source needs, such as a receiver for a `vn-eye` phone app.
- **Step 2 (deferred):** plugin loading and per-source configuration. Start it when a developer wants to write a source outside this repository, or when `vn-eye` gets a second built-in source.

A future source for these users, such as a phone app receiver, must be built in so that it works from the installer.

## Problems with the original design

This section describes the code before step 1. The boundary was the landmark backend (`landmarks.py`). Removing the MediaPipe backend (commit `b58f9c9`) also removed its settings (`eyes.metric`, `backend.delegate`) from the core config. Three leaks remained:

- **The app owned the camera.** `app.py` opened the webcam and passed frames to the backend, so a device without webcam frames (an eye tracker, a phone) could not be a backend.
- **The core assumed MediaPipe's landmark layout.** `eyes.py` and `preview.py` read fixed indices of the 478-point face mesh (`LEFT_EYE = (362, 385, …)`). A backend with another layout would give wrong eye values without an error.
- **Only one backend was possible.** `app.py` created `OpenCVBackend` directly, so adding another meant editing the main loop.

## Pipeline

The new pipeline has three stages. Each stage only talks to the next one.

```
Source                    core                                  core
──────                    ────                                  ────
owns its input      →     Signals  →  EyeStateTracker     →     Observation  →  triggers  →  outputs
(camera, model,           (raw         HeadTracker
 tracker device)           measurements) (baseline, median)
```

- A **source** owns its input device and its model, and reports raw measurements as `Signals`. Camera frames never leave the source.
- The **core** turns raw measurements into per-user, relative values: the rolling "eyes open" baseline (`EyeStateTracker`) and the rolling median head pose (`HeadTracker`). Every source gets this adaptation for free, so sources don't reimplement it.
- **Triggers** and **outputs** don't change. Triggers still receive `Observation`, emit fixed event names, and `output.actions` still maps events to outputs.

## Source contract

These types live in the internal module `vn_eye.sources` (`src/vn_eye/sources/__init__.py`), and only the built-in source uses them. Step 2 moves them to a public module, `vn_eye.api`, and adds `API_VERSION`. A plugin must import only from `vn_eye.api`. Everything else in `vn_eye` is internal and can change without notice.

```python
API_VERSION = 1  # added in step 2

EYE_OPENNESS = "eye_openness"
HEAD_POSE = "head_pose"


@dataclass(frozen=True)
class Signals:
    """What a source measured at one moment. A source fills only what it provides."""

    timestamp: float
    """Seconds, from time.monotonic()."""
    face_present: bool
    eye_openness: tuple[float, float] | None = None
    """(left, right) from the subject's view. 0 = fully closed; larger = more open.
    Any scale, as long as it is proportional and stable while the eyes stay open."""
    head_yaw_deg: float | None = None
    """Absolute head turn. Positive = toward the image's right."""
    head_pitch_deg: float | None = None
    """Absolute head tilt. Positive = head tilted down."""


class Source(Protocol):
    name: str
    provides: frozenset[str]
    """Signal names this source can fill, e.g. frozenset({EYE_OPENNESS, HEAD_POSE})."""

    def read(self) -> Signals:
        """Block until the next sample, for at most about 0.1 s.
        Return Signals(t, face_present=False) when there is no face or no data."""

    def debug_view(self) -> np.ndarray | None:
        """Optional BGR image for --preview, e.g. the camera frame with landmarks drawn.
        Return None if the source has nothing to show."""

    def close(self) -> None: ...
```

### Rules for sources

1. `eye_openness` must be proportional with 0 meaning closed. The core decides "closed" as a ratio of the open-eye baseline (`close_ratio = 0.55`), so a scale with an offset breaks it. Eye aspect ratio and `1 - eyeBlink` blendshape scores (for example from ARKit) both satisfy this. A device that only reports open or closed can send `1.0` and `0.0`.
2. A source handles its own device problems. For example, the webcam source reopens the camera when frames stop (the current `ReconnectingCamera`). During a gap, `read()` returns `face_present=False`, so triggers cancel half-done gestures as they do today.
3. Camera frames must stay inside the source. `debug_view()` is the only way an image leaves it, and the core only displays that image in the preview window.
4. A source must not write frames to disk or send them over the network (see [Privacy](#privacy)).

## Capabilities

Each trigger declares the signals it needs:

| Trigger | Needs | Uses if present |
|---|---|---|
| `blink` | `eye_openness` | `head_pose` (ignores blinks while the head is turned) |
| `head_shake` | `head_pose` | |
| `nod` | `head_pose` | |

At startup, the core compares each enabled trigger's needs with the source's `provides` and skips a trigger whose needs are missing, with a notice such as `head_shake: disabled (source tobii has no head_pose)`. `OpenCVSource` provides both signals, so the check never fails in step 1. It is part of step 1 anyway, so that a future source without head pose, such as an eye tracker, works without changes to the core.

## Plugin discovery

This section is deferred to step 2. Until then, `app.py` creates `OpenCVSource` directly.

A source plugin is a pip package that registers a class under the `vn_eye.sources` entry point group in its `pyproject.toml`:

```toml
[project.entry-points."vn_eye.sources"]
tobii = "vn_eye_tobii:TobiiSource"
```

The class must have:

- `api_version: int`. The core refuses to load a plugin whose `api_version` differs from `API_VERSION`, and names both versions in the error.
- `Options`: a frozen dataclass with defaults, the plugin's settings.
- `__init__(self, options: Options, log: Callable[[str], None])`.

The built-in `OpenCVSource` registers through the same entry point group in `vn-eye`'s own `pyproject.toml`. The core has no special case for built-in sources.

The core imports a plugin only when it is selected. Installed but unused plugins never run.

## Configuration

Step 1 didn't change the configuration: `OpenCVSource` reads the existing `[camera]` section.

In step 2, each source reads its options from its own section, `[source.<name>]`, and `[camera]` moves into `[source.opencv]`:

```toml
[source]
name = "opencv"

[source.opencv]
camera = 0
width = 640
height = 480
fps = 30

[source.tobii]   # only read when source.name = "tobii"
device = "auto"
```

- The core merges `[source.<name>]` into the source's `Options` dataclass with the same rules as the rest of the config: unknown keys are rejected, and `--set source.opencv.camera=1` works.
- Sections for sources that aren't selected are not validated, so one config file works on machines with different plugins installed.
- `--source NAME` selects the source. `--camera N` stays as a shortcut for `source.<selected>.camera`.
- `--help` lists the available sources: the built-in one and installed plugins.

## Preview

The preview window combines the source's `debug_view()` with an overlay that the core draws: state, eye values, baseline bar, trigger status, and FPS. The core draws the overlay on a blank canvas when the source returns `None`, so the preview also works for sources without a camera. The core mirrors the image, as it does today.

Drawing landmarks moves into the source, because only the source knows its landmark layout.

## Privacy

The privacy rule (frames stay in memory and are never written or sent) becomes structural for the core: the core never receives frames, only numbers and an optional debug image for the screen.

`vn-eye` cannot enforce the rule for third-party code. To make that visible:

- When the selected source comes from another package (step 2), the core prints one line at startup, for example `Using source "tobii" from vn-eye-tobii 0.1.0 (third-party code)`.
- The README states that the privacy guarantee covers `vn-eye`'s built-in sources only.

## Migration plan

Each step is one commit. Tests pass after every step.

1. **Introduce `Signals` and `Source` inside `vn-eye` (done).**
   - Move the camera, reconnect logic, OpenCV model code and EAR into `OpenCVSource`, which reads `[camera]`.
   - `EyeStateTracker` and `HeadTracker` consume `Signals` instead of `FaceFrame`. `FaceFrame` and the landmark indices disappear from the core.
   - Add the capability check.
   - Draw landmarks in the source's `debug_view()`, and draw the status overlay in the core.
   - Tests for `eyes.py` and `head.py` build `Signals` directly. EAR and landmark tests move to the OpenCV source's tests.
2. **Add plugin loading (deferred).** Move the contract to `vn_eye.api`, add `API_VERSION` and `api_version` checks, discover sources through entry points, and print the third-party notice. Replace `[camera]` with `[source]` and per-source options, and add `--source`. Register `OpenCVSource` through an entry point.

Each step also updates the docs it affects: README (config, flags, Layout), `config.example.toml`, and AGENTS.md (architecture, privacy, trigger checklist with `needs`).

Each step changes behavior only where stated. Gestures must behave the same afterward, which needs a live check (`vn-eye --preview --dry-run`) after step 1.

## Open questions

Both questions wait for step 2.

1. **Old config keys.** Step 2 moves `[camera]` into `[source.opencv]`. Should the core reject `[camera]` with a message that names the new section, or keep accepting it for one release?
2. **Triggers and outputs as plugins.** This design only makes sources pluggable. Making triggers and outputs pluggable can reuse the same mechanism later. It is out of scope until someone needs it.
