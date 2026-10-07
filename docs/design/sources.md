# Signal sources and plugins

Status: proposal. Nothing in this document is implemented yet.

This document describes how `vn-eye` separates *sensing* (camera, face model, eye tracker) from *recognizing gestures*, and how a third party can add a new sensing method as a separate pip package without changing `vn-eye` itself.

## Problems with the current design

The current boundary is the landmark backend (`landmarks.py`). It leaks in four ways:

- **The app owns the camera.** `app.py` opens the webcam and passes frames to the backend, so a device without webcam frames (an eye tracker, a phone) cannot be a backend.
- **The core assumes MediaPipe's landmark layout.** `eyes.py` and `preview.py` read fixed indices of the 478-point face mesh (`LEFT_EYE = (362, 385, …)`). A backend with another layout gives wrong eye values without an error.
- **Backend settings live in the core config.** `eyes.metric = "blendshape"` and `backend.delegate` only apply to MediaPipe. `app.py` needs a special check that rejects `blendshape` with the `opencv` backend.
- **Only built-in backends exist.** Adding one means editing `create_backend`.

## Pipeline

The new pipeline has three stages. Each stage only talks to the next one.

```
Source (plugin)           core                                  core
───────────────           ────                                  ────
owns its input      →     Signals  →  EyeStateTracker     →     Observation  →  triggers  →  outputs
(camera, model,           (raw         HeadTracker
 tracker device)           measurements) (baseline, median)
```

- A **source** owns its input device and its model, and reports raw measurements as `Signals`. Camera frames never leave the source.
- The **core** turns raw measurements into per-user, relative values: the rolling "eyes open" baseline (`EyeStateTracker`) and the rolling median head pose (`HeadTracker`). Every source gets this adaptation for free, so plugins don't reimplement it.
- **Triggers** and **outputs** don't change. Triggers still receive `Observation`, emit fixed event names, and `output.actions` still maps events to outputs.

## Source contract

The plugin API lives in one module, `vn_eye.api`. A plugin must import only from that module. Everything else in `vn_eye` is internal and can change without notice.

```python
API_VERSION = 1

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

1. `eye_openness` must be proportional with 0 meaning closed. The core decides "closed" as a ratio of the open-eye baseline (`close_ratio = 0.55`), so a scale with an offset breaks it. Eye aspect ratio and `1 - eyeBlink` blendshape scores both satisfy this. A device that only reports open or closed can send `1.0` and `0.0`.
2. A source handles its own device problems. For example, the webcam source reopens the camera when frames stop (the current `ReconnectingCamera`). During a gap, `read()` returns `face_present=False`, so triggers cancel half-done gestures as they do today.
3. Camera frames must stay inside the source. `debug_view()` is the only way an image leaves it, and the core only displays that image in the preview window.
4. A source must not write frames to disk or send them over the network (see [Privacy](#privacy)).

## Capabilities

Each trigger declares the signals it needs:

| Trigger | Needs | Uses if present |
|---|---|---|
| `blink` | `eye_openness` | `head_pose` (ignores blinks while the head is turned) |
| `head_shake` | `head_pose` | |
| `head_nod`, `nod` | `head_pose` | |

At startup, the core compares each enabled trigger's needs with the source's `provides`. This replaces backend-specific checks such as "blendshape needs mediapipe".

## Plugin discovery

A source plugin is a pip package that registers a class under the `vn_eye.sources` entry point group in its `pyproject.toml`:

```toml
[project.entry-points."vn_eye.sources"]
mediapipe = "vn_eye_mediapipe:MediaPipeSource"
```

The class must have:

- `api_version: int`. The core refuses to load a plugin whose `api_version` differs from `API_VERSION`, and names both versions in the error.
- `Options`: a frozen dataclass with defaults, the plugin's settings.
- `__init__(self, options: Options, log: Callable[[str], None])`.

The built-in OpenCV source registers through the same entry point group in `vn-eye`'s own `pyproject.toml`. The core has no special case for built-in sources.

The core imports a plugin only when it is selected. Installed but unused plugins never run.

## Configuration

`[camera]`, `[backend]` and `eyes.metric` move into per-source sections. Each source reads its options from `[source.<name>]`:

```toml
[source]
name = "opencv"

[source.opencv]
camera = 0
width = 640
height = 480
fps = 30

[source.mediapipe]   # only read when source.name = "mediapipe"
camera = 0
delegate = "auto"
metric = "blendshape"
```

- The core merges `[source.<name>]` into the plugin's `Options` dataclass with the same rules as the rest of the config: unknown keys are rejected, and `--set source.opencv.camera=1` works.
- Sections for sources that aren't selected are not validated, so one config file works on machines with different plugins installed.
- `--source NAME` selects the source. `--camera N` stays as a shortcut for `source.<selected>.camera`.
- `--help` lists the installed sources.

## Preview

The preview window combines the source's `debug_view()` with an overlay that the core draws: state, eye values, baseline bar, trigger status, and FPS. The core draws the overlay on a blank canvas when the source returns `None`, so the preview also works for sources without a camera. The core mirrors the image, as it does today.

Drawing landmarks moves into the source, because only the source knows its landmark layout.

## Privacy

The privacy rule (frames stay in memory and are never written or sent) becomes structural for the core: the core never receives frames, only numbers and an optional debug image for the screen.

`vn-eye` cannot enforce the rule for third-party code. To make that visible:

- When the selected source comes from another package, the core prints one line at startup, for example `Using source "mediapipe" from vn-eye-mediapipe 0.1.0 (third-party code)`.
- The README states that the privacy guarantee covers `vn-eye`'s built-in sources only.

## Migration plan

Each step is one commit. Tests pass after every step.

1. **Introduce `Signals` and `Source` inside `vn-eye`.**
   - Move the camera, reconnect logic, OpenCV model code and EAR into `OpenCVSource`. Move `MediaPipeBackend` into `MediaPipeSource` (still built in for now).
   - `EyeStateTracker` and `HeadTracker` consume `Signals` instead of `FaceFrame`. `FaceFrame` and `eyes.metric` disappear from the core.
   - Add capability checks. Replace `[camera]` and `[backend]` with `[source]`.
   - Tests for `eyes.py` and `head.py` build `Signals` directly. EAR and landmark tests move to the OpenCV source's tests.
2. **Add plugin loading.** Add `vn_eye.api`, entry point discovery, `api_version` checks, per-source options, the third-party notice, and `--source`. Register both built-in sources through entry points.
3. **Move MediaPipe out** into its own package. The `mediapipe` extra in `pyproject.toml` goes away.
4. **Update docs** in each step: README (config, flags, Layout), `config.example.toml`, AGENTS.md (architecture, privacy, trigger checklist with `needs`).

Each step changes behavior only where stated. Gestures must behave the same afterward, which needs a live check (`vn-eye --preview --dry-run`) after steps 1 and 3.

## Open questions

1. **Missing capabilities.** When an enabled trigger needs a signal the source doesn't provide, should the core stop with an error, or skip that trigger and print a notice? Skipping is friendlier for sources without head pose, because `head_shake` is on by default. An error is more explicit.
2. **Old config keys.** `[camera]`, `[backend]` and `eyes.metric` stop working. Should the core reject them with a message that names the new key, or keep accepting them for one release?
3. **Where the MediaPipe plugin lives.** In this repository as a second package (`plugins/vn-eye-mediapipe/`), which keeps it in step with API changes, or in its own repository, which proves that outside authors can build plugins?
4. **Triggers and outputs as plugins.** This design only makes sources pluggable. Making triggers and outputs pluggable can reuse the same mechanism later. It is out of scope until someone needs it.
