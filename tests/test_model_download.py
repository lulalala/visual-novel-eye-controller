import hashlib
import urllib.request

import pytest

from eyeokuri.sources import face_mesh

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

    monkeypatch.setattr(face_mesh, "MODEL_SHA256", hashlib.sha256(GOOD).hexdigest())
    monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)
    return downloads, served


def test_model_url_is_pinned_to_a_version():
    assert "/latest/" not in face_mesh.MODEL_URL
    assert len(face_mesh.MODEL_SHA256) == 64


def test_matching_cached_model_is_not_downloaded_again(tmp_path, pinned):
    downloads, _ = pinned
    path = tmp_path / "face_landmarker.task"
    path.write_bytes(GOOD)
    assert face_mesh.ensure_model(path) == path
    assert downloads == []


def test_missing_model_is_downloaded_and_verified(tmp_path, pinned):
    downloads, _ = pinned
    path = tmp_path / "cache" / "face_landmarker.task"
    face_mesh.ensure_model(path)
    assert path.read_bytes() == GOOD
    assert downloads == [face_mesh.MODEL_URL]


def test_cached_model_of_another_version_is_replaced(tmp_path, pinned):
    downloads, _ = pinned
    path = tmp_path / "face_landmarker.task"
    path.write_bytes(BAD)
    face_mesh.ensure_model(path)
    assert path.read_bytes() == GOOD
    assert len(downloads) == 1


def test_download_with_wrong_hash_is_rejected_and_discarded(tmp_path, pinned):
    _, served = pinned
    served["data"] = BAD
    path = tmp_path / "face_landmarker.task"
    with pytest.raises(SystemExit, match="SHA-256"):
        face_mesh.ensure_model(path)
    assert list(tmp_path.iterdir()) == []


def test_bundled_model_is_copied_to_the_cache_without_downloading(tmp_path, pinned, monkeypatch):
    downloads, _ = pinned
    (tmp_path / "app" / "model").mkdir(parents=True)
    (tmp_path / "app" / "model" / "face_landmarker.task").write_bytes(GOOD)
    monkeypatch.setattr(face_mesh.sys, "_MEIPASS", str(tmp_path / "app"), raising=False)
    monkeypatch.setattr(face_mesh, "cache_dir", lambda: tmp_path / "cache")
    path = face_mesh.ensure_model()
    assert path == tmp_path / "cache" / "face_landmarker.task"
    assert path.read_bytes() == GOOD
    assert downloads == []
