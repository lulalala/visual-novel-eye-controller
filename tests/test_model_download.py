import hashlib
import urllib.request

import pytest

from vn_eye import landmarks

GOOD = b"pinned model"
BAD = b"some other model"


@pytest.fixture
def pinned(monkeypatch):
    """Pins the model to GOOD and records downloads, which serve the bytes in ``served``."""
    downloads = []
    served = {"data": GOOD}

    def fake_urlretrieve(url, filename):
        downloads.append(url)
        with open(filename, "wb") as f:
            f.write(served["data"])

    monkeypatch.setattr(landmarks, "MODEL_SHA256", hashlib.sha256(GOOD).hexdigest())
    monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)
    return downloads, served


def test_model_url_is_pinned_to_a_version():
    assert "/latest/" not in landmarks.MODEL_URL
    assert len(landmarks.MODEL_SHA256) == 64


def test_matching_cached_model_is_not_downloaded_again(tmp_path, pinned):
    downloads, _ = pinned
    path = tmp_path / "face_landmarker.task"
    path.write_bytes(GOOD)
    assert landmarks.ensure_model(path) == path
    assert downloads == []


def test_missing_model_is_downloaded_and_verified(tmp_path, pinned):
    downloads, _ = pinned
    path = tmp_path / "cache" / "face_landmarker.task"
    landmarks.ensure_model(path)
    assert path.read_bytes() == GOOD
    assert downloads == [landmarks.MODEL_URL]


def test_cached_model_of_another_version_is_replaced(tmp_path, pinned):
    downloads, _ = pinned
    path = tmp_path / "face_landmarker.task"
    path.write_bytes(BAD)
    landmarks.ensure_model(path)
    assert path.read_bytes() == GOOD
    assert len(downloads) == 1


def test_download_with_wrong_hash_is_rejected_and_discarded(tmp_path, pinned):
    _, served = pinned
    served["data"] = BAD
    path = tmp_path / "face_landmarker.task"
    with pytest.raises(SystemExit, match="SHA-256"):
        landmarks.ensure_model(path)
    assert list(tmp_path.iterdir()) == []
