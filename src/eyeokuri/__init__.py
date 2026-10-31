"""Advance visual novels with eye gestures."""

from __future__ import annotations

import os
import sys

__version__ = "0.2.0"

if sys.platform == "win32":
    # Media Foundation's hardware conversion makes opening the camera take
    # seconds longer (3.1s vs 0.8s here, up to ~10s). OpenCV reads this once
    # when it loads, so it must be set before any module imports cv2.
    os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")
