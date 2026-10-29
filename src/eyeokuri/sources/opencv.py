"""The built-in source: a webcam and MediaPipe's face mesh, run with OpenCV."""

from __future__ import annotations

import time
from typing import Callable

import cv2
import numpy as np

from eyeokuri.config import CameraConfig
from eyeokuri.sources import EYE_OPENNESS, HEAD_POSE, Signals
from eyeokuri.sources.camera import open_camera
from eyeokuri.sources.face_mesh import FaceMesh, head_pose_from_landmarks

# Face mesh indices, ordered p1..p6 for the eye aspect ratio: p1/p4 are the
# eye corners, (p2, p6) and (p3, p5) are upper/lower lid pairs.
# "Left"/"right" are from the subject's point of view.
LEFT_EYE = (362, 385, 387, 263, 373, 380)
RIGHT_EYE = (33, 160, 158, 133, 153, 144)

_EYE_COLOR = (230, 200, 40)


def eye_aspect_ratio(points: np.ndarray, idx: tuple[int, ...]) -> float:
    """Soukupová & Čech (2016) EAR: ~0.25-0.35 when open, near 0 when closed."""
    p = points[list(idx), :2]
    vertical = np.linalg.norm(p[1] - p[5]) + np.linalg.norm(p[2] - p[4])
    horizontal = np.linalg.norm(p[0] - p[3])
    if horizontal < 1e-6:
        return 0.0
    return float(vertical / (2.0 * horizontal))


def signals_from_landmarks(timestamp: float, landmarks: np.ndarray | None) -> Signals:
    """Eye aspect ratios and head pose from face mesh landmarks (None = no face)."""
    if landmarks is None:
        return Signals(timestamp, face_present=False)
    yaw, pitch, roll = head_pose_from_landmarks(landmarks)
    return Signals(
        timestamp,
        face_present=True,
        eye_openness=(eye_aspect_ratio(landmarks, LEFT_EYE), eye_aspect_ratio(landmarks, RIGHT_EYE)),
        head_yaw_deg=yaw,
        head_pitch_deg=pitch,
        head_roll_deg=roll,
    )


class OpenCVSource:
    """Webcam frames -> face mesh -> eye aspect ratios and head pose."""

    name = "opencv"
    provides = frozenset({EYE_OPENNESS, HEAD_POSE})

    def __init__(self, camera: CameraConfig, log: Callable[[str], None] | None = None) -> None:
        self._camera = open_camera(camera, log)
        self._mesh = FaceMesh()
        self._frame: np.ndarray | None = None
        self._landmarks: np.ndarray | None = None

    def read(self) -> Signals:
        now = time.monotonic()
        self._frame = self._camera.read(now)
        if self._frame is None:
            self._landmarks = None
            # The camera is reconnecting; wait instead of spinning.
            time.sleep(0.1)
            return Signals(now, face_present=False)
        self._landmarks = self._mesh.process(self._frame)
        return signals_from_landmarks(now, self._landmarks)

    def debug_view(self) -> np.ndarray | None:
        if self._frame is None:
            return None
        img = self._frame.copy()
        if self._landmarks is not None:
            for idx in (LEFT_EYE, RIGHT_EYE):
                pts = self._landmarks[list(idx), :2].astype(np.int32)
                cv2.polylines(img, [pts], isClosed=True, color=_EYE_COLOR, thickness=1)
        return img

    def close(self) -> None:
        self._camera.release()
