"""Webcam capture that reopens the camera when it stops delivering frames."""

from __future__ import annotations

from typing import Any, Callable

import cv2

from vn_eye.config import CameraConfig

# While frames keep failing, reopen the camera this often.
_RECONNECT_AFTER_S = 1.0


class ReconnectingCamera:
    """Reads frames and reopens the camera when it stops delivering them."""

    def __init__(
        self,
        open_capture: Callable[[], Any],
        reconnect_after_s: float,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self._open_capture = open_capture
        self._reconnect_after_s = reconnect_after_s
        self._log = log
        self._cap = open_capture()
        self._failing_since: float | None = None
        self._last_attempt = 0.0

    @property
    def opened(self) -> bool:
        return bool(self._cap.isOpened())

    def read(self, now: float) -> Any | None:
        ok, frame = self._cap.read()
        if ok:
            if self._failing_since is not None:
                self._say(f"camera: frames are back after {now - self._failing_since:.2f}s")
                self._failing_since = None
            return frame
        if self._failing_since is None:
            self._failing_since = now
            self._last_attempt = now
            self._say("camera: frame grab failed (retrying)")
        elif now - self._last_attempt >= self._reconnect_after_s:
            # On Windows a device reset (MF_E_VIDEO_RECORDING_DEVICE_INVALIDATED)
            # kills the capture handle for good; only a fresh one recovers.
            self._last_attempt = now
            self._say("camera: reopening")
            self._cap.release()
            self._cap = self._open_capture()
        return None

    def release(self) -> None:
        self._cap.release()

    def _say(self, message: str) -> None:
        if self._log:
            self._log(message)


def _open_capture(cam: CameraConfig) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(cam.index)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam.height)
        cap.set(cv2.CAP_PROP_FPS, cam.fps)
    return cap


def open_camera(cam: CameraConfig, log: Callable[[str], None] | None = None) -> ReconnectingCamera:
    camera = ReconnectingCamera(lambda: _open_capture(cam), _RECONNECT_AFTER_S, log)
    if not camera.opened:
        raise SystemExit(
            f"Could not open camera {cam.index}. Check that no other app is using it "
            "and that this terminal has camera permission."
        )
    return camera
