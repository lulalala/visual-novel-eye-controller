"""Optional debug window: the source's view with eye and trigger state drawn on top."""

from __future__ import annotations

import cv2
import numpy as np

from vn_eye.config import EyeConfig
from vn_eye.eyes import Observation

WINDOW = "vn-eye preview"
# Canvas for sources without an image, so the status overlay still shows.
_BLANK_SIZE = (480, 640)

_GREEN = (80, 200, 80)
_RED = (60, 60, 230)
_YELLOW = (40, 200, 230)
_WHITE = (240, 240, 240)
_GRAY = (140, 140, 140)


def _text(img: np.ndarray, text: str, y: int, color=_WHITE) -> None:
    cv2.putText(img, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)


def _openness_bar(img: np.ndarray, obs: Observation, cfg: EyeConfig) -> None:
    if obs.combined is None or obs.baseline is None:
        return
    h, w = img.shape[:2]
    x0, x1, y0, y1 = 10, w - 10, h - 30, h - 14
    scale = (x1 - x0) / max(obs.baseline * 1.5, 1e-6)

    def x(v: float) -> int:
        return int(x0 + min(v * scale, x1 - x0))

    cv2.rectangle(img, (x0, y0), (x1, y1), _GRAY, 1)
    cv2.rectangle(img, (x0, y0), (x(obs.combined), y1), _RED if obs.closed else _GREEN, -1)
    for v, color in (
        (obs.baseline * cfg.close_ratio, _RED),
        (obs.baseline * cfg.open_ratio, _YELLOW),
        (obs.baseline, _WHITE),
    ):
        cv2.line(img, (x(v), y0 - 4), (x(v), y1 + 4), color, 2)


def show(
    view: np.ndarray | None,
    obs: Observation,
    eye_cfg: EyeConfig,
    trigger_status: list[str],
    paused: bool,
    fps: float,
    flash: bool,
) -> int:
    """Draw and display one frame; returns the pressed key code (or -1)."""
    if view is None:
        img = np.zeros((*_BLANK_SIZE, 3), dtype=np.uint8)
    else:
        img = cv2.flip(view, 1)  # mirror, so it behaves like a mirror for the user

    if flash:
        cv2.rectangle(img, (0, 0), (img.shape[1] - 1, img.shape[0] - 1), _YELLOW, 12)

    y = 24
    state = "PAUSED" if paused else ("no face" if not obs.face_present else
                                     ("calibrating..." if not obs.ready else
                                      ("CLOSED" if obs.closed else "open")))
    _text(img, f"{state}   {fps:4.1f} fps", y, _YELLOW if paused or not obs.ready else _WHITE)
    if obs.left is not None:
        y += 22
        base = f"{obs.baseline:.3f}" if obs.baseline is not None else "-"
        _text(img, f"L {obs.left:.3f}  R {obs.right:.3f}  baseline {base}", y)
    for line in trigger_status:
        y += 22
        _text(img, line, y)
    _text(img, "p: pause   q/Esc: quit", img.shape[0] - 40, _GRAY)
    _openness_bar(img, obs, eye_cfg)

    cv2.imshow(WINDOW, img)
    return cv2.waitKey(1) & 0xFF


def close() -> None:
    cv2.destroyAllWindows()
