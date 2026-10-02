"""Face landmark backends.

A backend turns a camera frame into a ``FaceFrame``. Everything downstream
(eye metrics, triggers) only sees ``FaceFrame``, so other backends (EyeTrax,
GazeFollower, a Tobii tracker) can be added without touching the triggers.
"""

from __future__ import annotations

import math
import os
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/latest/face_landmarker.task"
)


@dataclass(frozen=True)
class FaceFrame:
    timestamp: float
    """Seconds, from a monotonic clock."""
    landmarks: np.ndarray | None
    """(N, 3) landmarks in pixel coordinates (z is relative depth), or None if no face."""
    blendshapes: dict[str, float] | None = None
    """Optional named expression scores in [0, 1], e.g. ``eyeBlinkLeft``."""
    head_yaw_deg: float | None = None
    """Absolute head turn left/right in degrees, if the backend estimates head pose."""
    head_pitch_deg: float | None = None
    """Absolute head tilt up/down in degrees (positive = up), if available."""


class LandmarkBackend(Protocol):
    def process(self, frame_bgr: np.ndarray, timestamp: float) -> FaceFrame: ...

    def close(self) -> None: ...


def cache_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "vn-eye"


def ensure_model(path: Path | None = None) -> Path:
    path = path or cache_dir() / "face_landmarker.task"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"Downloading face landmark model to {path} ...", flush=True)
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(MODEL_URL, tmp)
        tmp.replace(path)
    return path


class MediaPipeBackend:
    """MediaPipe Face Landmarker (478 face + iris landmarks, 52 blendshapes)."""

    def __init__(self, delegate: str = "auto", model_path: Path | None = None) -> None:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python import vision

        if delegate == "auto":
            # mediapipe 1.0.1's CPU graph aborts on macOS (it still asks for a
            # Metal service), while the GPU delegate isn't available on Windows.
            delegate = "gpu" if sys.platform == "darwin" else "cpu"
        if delegate not in ("cpu", "gpu"):
            raise ValueError(f"Unknown MediaPipe delegate: {delegate}")
        self._mp = mp
        # The GPU path only accepts 4-channel images.
        self._rgba = delegate == "gpu"
        options = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(
                model_asset_path=str(ensure_model(model_path)),
                delegate=BaseOptions.Delegate.GPU if delegate == "gpu" else BaseOptions.Delegate.CPU,
            ),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)
        self._last_ts_ms = -1

    def process(self, frame_bgr: np.ndarray, timestamp: float) -> FaceFrame:
        h, w = frame_bgr.shape[:2]
        if self._rgba:
            data = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGBA)
            image = self._mp.Image(image_format=self._mp.ImageFormat.SRGBA, data=data)
        else:
            data = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=data)
        # VIDEO mode requires strictly increasing timestamps.
        ts_ms = max(int(timestamp * 1000), self._last_ts_ms + 1)
        self._last_ts_ms = ts_ms
        result = self._landmarker.detect_for_video(image, ts_ms)

        if not result.face_landmarks:
            return FaceFrame(timestamp, None)
        points = np.array(
            [(p.x * w, p.y * h, p.z * w) for p in result.face_landmarks[0]],
            dtype=np.float32,
        )
        blendshapes = None
        if result.face_blendshapes:
            blendshapes = {c.category_name: c.score for c in result.face_blendshapes[0]}
        yaw = None
        pitch = None
        if result.facial_transformation_matrixes:
            r = np.asarray(result.facial_transformation_matrixes[0])[:3, :3]
            yaw = math.degrees(math.atan2(r[0, 2], r[2, 2]))
            pitch = math.degrees(math.atan2(-r[1, 2], r[2, 2]))
        return FaceFrame(timestamp, points, blendshapes, yaw, pitch)

    def close(self) -> None:
        self._landmarker.close()


def create_backend(name: str = "mediapipe", delegate: str = "auto") -> LandmarkBackend:
    if name == "mediapipe":
        return MediaPipeBackend(delegate)
    raise ValueError(f"Unknown landmark backend: {name}")
