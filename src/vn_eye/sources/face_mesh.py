"""MediaPipe's face mesh (478 face + iris landmarks) from a camera frame, run with OpenCV."""

from __future__ import annotations

import hashlib
import math
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

import cv2
import numpy as np

# Pinned to version 1: FaceMesh relies on this model's input sizes, output
# names and anchor layout, which a newer "latest" model could change.
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"


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


# MediaPipe's face detector and face mesh models, from face_landmarker.task, run
# with OpenCV instead of the mediapipe package (which includes telemetry).
_DETECTOR_SIZE = 128
_MESH_SIZE = 256
# A face crop is the face box (or the landmark bounds) enlarged by this factor.
_ROI_SCALE = 1.5
# Mesh indices for the head axes: outer eye corners, top of forehead, chin.
_RIGHT_EYE_OUTER, _LEFT_EYE_OUTER, _FOREHEAD, _CHIN = 33, 263, 10, 152


def head_pose_from_landmarks(points: np.ndarray) -> tuple[float, float]:
    """(yaw, pitch) in degrees from 3D mesh landmarks in image axes (x right, y down,
    z away from the camera). Positive yaw = face turned toward the image's right;
    positive pitch = head tilted down."""
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


class FaceMesh:
    """MediaPipe's face detector and face mesh models (478 face + iris landmarks),
    run with OpenCV's DNN module."""

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

    def process(self, frame_bgr: np.ndarray) -> np.ndarray | None:
        """(478, 3) landmarks in frame pixels (z is relative depth), or None if no face."""
        points = self._fit(frame_bgr, *self._roi) if self._roi is not None else None
        if points is None:
            roi = self._detect(frame_bgr)
            points = self._fit(frame_bgr, *roi) if roi is not None else None
        self._roi = _roi_from_landmarks(points) if points is not None else None
        return points

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
