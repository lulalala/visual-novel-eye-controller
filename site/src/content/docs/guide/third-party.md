---
title: Third-party software
sidebar:
  order: 99
description: The models and libraries that eyeokuri includes, who made them, and under which licenses.
---

eyeokuri builds on the work of others. This page lists what the Windows build includes. The repository keeps the same list, with the full license text, in [THIRD_PARTY_NOTICES.md](https://github.com/lulalala/visual-novel-eye-controller/blob/master/THIRD_PARTY_NOTICES.md).

## Face model

eyeokuri finds your face and eyes with the MediaPipe Face Landmarker models from Google. The file is `face_landmarker.task` (version 1, float16), unmodified. It bundles three models:

- BlazeFace Short Range, which detects a face.
- Face Mesh V2, which places 478 landmarks on it.
- Blendshape V2.

The first run downloads the file from [Google's model storage](https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task). Read the [model card](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker) for details. The models use the [Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0).

eyeokuri runs the model through OpenCV. It does not use the `mediapipe` package.

eyeokuri is not affiliated with or endorsed by Google. "MediaPipe" and "Google" are trademarks of Google LLC.

## Python packages

The executable also contains Python, OpenCV and NumPy, which have their own licenses:

- [OpenCV license](https://github.com/opencv/opencv/blob/4.x/LICENSE)
- [NumPy license](https://github.com/numpy/numpy/blob/main/LICENSE.txt)
- [Python license](https://docs.python.org/3/license.html)
