"""Face landmark backends.

A backend turns a camera frame into a ``FaceFrame``. Everything downstream
(eye metrics, triggers) only sees ``FaceFrame``, so other backends (EyeTrax,
GazeFollower, a Tobii tracker) can be added without touching the triggers.
"""

from __future__ import annotations

import hashlib
import math
import os
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

# Pinned to version 1: OpenCVBackend relies on this model's input sizes, output
# names and anchor layout, which a newer "latest" model could change.
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"


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
    """Absolute head tilt up/down in degrees (positive = down), if available."""


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


def _sha256(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def ensure_model(path: Path | None = None) -> Path:
    path = path or cache_dir() / "face_landmarker.task"
    if path.exists() and _sha256(path) == MODEL_SHA256:
        return path
    if path.exists():
        print(f"Cached face landmark model at {path} is not the pinned version; downloading it again.")
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading face landmark model to {path} ...", flush=True)
    tmp = path.with_suffix(".part")
    urllib.request.urlretrieve(MODEL_URL, tmp)
    digest = _sha256(tmp)
    if digest != MODEL_SHA256:
        tmp.unlink()
        raise SystemExit(
            f"Downloaded face landmark model has SHA-256 {digest}, expected {MODEL_SHA256}; "
            "not using it. Run vn-eye again to retry the download."
        )
    tmp.replace(path)
    return path


class MediaPipeBackend:
    """MediaPipe Face Landmarker (478 face + iris landmarks, 52 blendshapes)."""

    def __init__(self, delegate: str = "auto", model_path: Path | None = None) -> None:
        try:
            import mediapipe as mp
        except ImportError:
            raise SystemExit(
                'backend.name "mediapipe" needs the mediapipe package. '
                'Install it with: pip install -e ".[mediapipe]"'
            ) from None
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


# MediaPipe's own models, run with OpenCV instead of the mediapipe package.
# Both are inside the same face_landmarker.task file that MediaPipeBackend uses.
_DETECTOR_SIZE = 128
_MESH_SIZE = 256
# A face crop is the face box (or the landmark bounds) enlarged by this factor.
_ROI_SCALE = 1.5
# Mesh indices for the head axes: outer eye corners, top of forehead, chin.
_RIGHT_EYE_OUTER, _LEFT_EYE_OUTER, _FOREHEAD, _CHIN = 33, 263, 10, 152


def head_pose_from_landmarks(points: np.ndarray) -> tuple[float, float]:
    """(yaw, pitch) in degrees from 3D mesh landmarks in image axes (x right, y down,
    z away from the camera). Same signs as MediaPipeBackend: positive pitch = head down."""
    across = points[_LEFT_EYE_OUTER] - points[_RIGHT_EYE_OUTER]
    down = points[_CHIN] - points[_FOREHEAD]
    forward = np.cross(down, across)  # out of the face, toward the camera
    yaw = math.degrees(math.atan2(forward[0], -forward[2]))
    pitch = math.degrees(math.atan2(forward[1], -forward[2]))
    return yaw, pitch


def detector_anchors() -> np.ndarray:
    """(896, 2) anchor centers of the short-range BlazeFace model, normalized to [0, 1]."""
    centers: list[tuple[float, float]] = []
    for stride, per_cell in ((8, 2), (16, 6)):
        cells = _DETECTOR_SIZE // stride
        for y in range(cells):
            for x in range(cells):
                centers.extend([((x + 0.5) / cells, (y + 0.5) / cells)] * per_cell)
    return np.array(centers, dtype=np.float32)


def crop_transform(
    center: tuple[float, float], size: float, angle: float, out_size: int
) -> np.ndarray:
    """2x3 affine that maps crop pixels to frame pixels, for a square crop of side
    ``size`` around ``center`` rotated by ``angle`` radians."""
    scale = size / out_size
    c, s = math.cos(angle) * scale, math.sin(angle) * scale
    m = np.array([[c, -s, 0.0], [s, c, 0.0]], dtype=np.float32)
    m[:, 2] = np.asarray(center, dtype=np.float32) - m[:, :2] @ np.full(2, out_size / 2, np.float32)
    return m


def _roi_from_landmarks(points: np.ndarray) -> tuple[tuple[float, float], float, float]:
    lo, hi = points[:, :2].min(axis=0), points[:, :2].max(axis=0)
    eyes = points[_LEFT_EYE_OUTER, :2] - points[_RIGHT_EYE_OUTER, :2]
    center = (float(lo[0] + hi[0]) / 2, float(lo[1] + hi[1]) / 2)
    return center, float((hi - lo).max()) * _ROI_SCALE, math.atan2(eyes[1], eyes[0])


def _extract(task: Path, member: str) -> Path:
    """Unpack one model from the .task bundle into the cache, next to the bundle."""
    path = task.parent / member
    if not path.exists() or path.stat().st_mtime < task.stat().st_mtime:
        tmp = path.with_suffix(".part")
        with zipfile.ZipFile(task) as bundle:
            tmp.write_bytes(bundle.read(member))
        tmp.replace(path)
    return path


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(min(x, 80.0), -80.0)))


class OpenCVBackend:
    """MediaPipe's face detector and face mesh models (478 face + iris landmarks),
    run with OpenCV's DNN module. No blendshapes; head pose comes from the mesh."""

    def __init__(self, model_path: Path | None = None, min_confidence: float = 0.5) -> None:
        task = ensure_model(model_path)
        self._detector = self._read_net(_extract(task, "face_detector.tflite"))
        self._mesh = self._read_net(_extract(task, "face_landmarks_detector.tflite"))
        self._anchors = detector_anchors()
        self._min_confidence = min_confidence
        # Crop from the previous frame's landmarks; the detector only runs when tracking is lost.
        self._roi: tuple[tuple[float, float], float, float] | None = None

    @staticmethod
    def _read_net(path: Path) -> cv2.dnn.Net:
        # OpenCV 5's new engine exposes only one output of these models. Loading
        # from a path, because the in-memory loader ignores the engine argument.
        engine = getattr(cv2.dnn, "ENGINE_CLASSIC", None)
        if engine is None:
            return cv2.dnn.readNetFromTFLite(str(path))
        return cv2.dnn.readNetFromTFLite(str(path), engine)

    def process(self, frame_bgr: np.ndarray, timestamp: float) -> FaceFrame:
        points = self._fit(frame_bgr, *self._roi) if self._roi is not None else None
        if points is None:
            roi = self._detect(frame_bgr)
            points = self._fit(frame_bgr, *roi) if roi is not None else None
        if points is None:
            self._roi = None
            return FaceFrame(timestamp, None)
        self._roi = _roi_from_landmarks(points)
        yaw, pitch = head_pose_from_landmarks(points)
        return FaceFrame(timestamp, points, None, yaw, pitch)

    def _detect(self, frame_bgr: np.ndarray) -> tuple[tuple[float, float], float, float] | None:
        h, w = frame_bgr.shape[:2]
        # Pad to a square so the face keeps its aspect ratio, as MediaPipe does.
        side = max(h, w)
        top, left = (side - h) // 2, (side - w) // 2
        square = cv2.copyMakeBorder(
            frame_bgr, top, side - h - top, left, side - w - left, cv2.BORDER_CONSTANT
        )
        rgb = cv2.cvtColor(cv2.resize(square, (_DETECTOR_SIZE, _DETECTOR_SIZE)), cv2.COLOR_BGR2RGB)
        self._detector.setInput((rgb.astype(np.float32) / 127.5 - 1.0).transpose(2, 0, 1)[None])
        regressors, scores = self._detector.forward(["regressors", "classificators"])
        best = int(np.argmax(scores[0, :, 0]))
        if _sigmoid(float(scores[0, best, 0])) < self._min_confidence:
            return None
        r = regressors[0, best] / _DETECTOR_SIZE
        anchor = self._anchors[best]
        center = (float((anchor[0] + r[0]) * side - left), float((anchor[1] + r[1]) * side - top))
        size = float(max(r[2], r[3])) * side * _ROI_SCALE
        # Keypoints 0 and 1 are the subject's right and left eye.
        return center, size, math.atan2(r[7] - r[5], r[6] - r[4])

    def _fit(
        self, frame_bgr: np.ndarray, center: tuple[float, float], size: float, angle: float
    ) -> np.ndarray | None:
        m = crop_transform(center, size, angle, _MESH_SIZE)
        crop = cv2.warpAffine(
            frame_bgr, m, (_MESH_SIZE, _MESH_SIZE), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR
        )
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        self._mesh.setInput((rgb.astype(np.float32) / 255.0).transpose(2, 0, 1)[None])
        landmarks, presence = self._mesh.forward(["Identity", "Identity_1"])
        if _sigmoid(float(presence.ravel()[0])) < self._min_confidence:
            return None
        local = landmarks.reshape(-1, 3)
        xy = local[:, :2] @ m[:, :2].T + m[:, 2]
        z = local[:, 2:] * (size / _MESH_SIZE)
        return np.hstack([xy, z]).astype(np.float32)

    def close(self) -> None:
        pass


BACKEND_NAMES = ("mediapipe", "opencv")


def create_backend(name: str = "mediapipe", delegate: str = "auto") -> LandmarkBackend:
    if name == "mediapipe":
        return MediaPipeBackend(delegate)
    if name == "opencv":
        return OpenCVBackend()
    raise ValueError(f"backend.name must be one of {', '.join(BACKEND_NAMES)}, not {name!r}")
