"""sha256 perception cache + gateway cache integration (design 12.4, NFR-082)."""
import hashlib
import os
import time

import pytest

from apps.inference_gateway import adapters
from apps.inference_gateway.cache import InferenceCache, sha256_file
from apps.inference_gateway.gateway import InferenceGateway


@pytest.fixture
def file_cache_env(tmp_path, monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("INFERENCE_CACHE_DIR", str(tmp_path / "cache"))
    return tmp_path


@pytest.fixture
def image(tmp_path):
    p = tmp_path / "screen.png"
    p.write_bytes(b"fake-image-bytes")
    return str(p)


def test_sha256_file(tmp_path):
    p = tmp_path / "a.bin"
    p.write_bytes(b"hello")
    assert sha256_file(str(p)) == hashlib.sha256(b"hello").hexdigest()


def test_file_cache_roundtrip(file_cache_env):
    c = InferenceCache()
    key = "infer:detection:omniparser-v2:abc123"
    assert c.get(key) is None
    c.set(key, {"elements": [1, 2]})
    assert c.get(key) == {"elements": [1, 2]}


def test_file_cache_ttl_expiry(file_cache_env):
    c = InferenceCache(ttl_s=5)
    c.set("k", {"v": 1})
    path = c._path("k")
    old = time.time() - 60
    os.utime(path, (old, old))
    assert c.get("k") is None


def test_cache_write_failure_never_raises(file_cache_env, monkeypatch):
    c = InferenceCache()
    blocker = file_cache_env / "blocker"
    blocker.write_text("not a directory")
    monkeypatch.setenv("INFERENCE_CACHE_DIR", str(blocker / "sub"))  # mkdir will fail
    c.set("k", {"v": 1})  # must not raise


def test_gateway_caches_detection_by_image_hash(file_cache_env, image, monkeypatch):
    calls = {"n": 0}

    def fake_detect(image_path, device="cuda"):
        calls["n"] += 1
        return [{"type": "interactable", "bbox": [0, 0, 0.1, 0.1],
                 "confidence": 0.9, "caption": "Save"}]

    monkeypatch.setattr(adapters, "detect_elements", fake_detect)
    g = InferenceGateway("local-6gb")

    r1 = g.infer("detection", {"image_path": image})
    assert r1["elements"][0]["caption"] == "Save"
    assert "cached" not in r1

    r2 = g.infer("detection", {"image_path": image})
    assert r2["cached"] is True
    assert r2["elements"] == r1["elements"]
    assert calls["n"] == 1  # second call never hit the backend


def test_gateway_cache_distinguishes_images(file_cache_env, image, tmp_path, monkeypatch):
    other = tmp_path / "other.png"
    other.write_bytes(b"different-image-bytes")
    calls = {"n": 0}

    def fake_detect(image_path, device="cuda"):
        calls["n"] += 1
        return [{"type": "interactable", "bbox": [0, 0, 0.1, 0.1],
                 "confidence": 0.9, "caption": None}]

    monkeypatch.setattr(adapters, "detect_elements", fake_detect)
    g = InferenceGateway("local-6gb")
    g.infer("detection", {"image_path": image})
    g.infer("detection", {"image_path": str(other)})
    assert calls["n"] == 2


def test_mock_profile_is_never_cached(file_cache_env, image):
    g = InferenceGateway("mock")
    r1 = g.infer("detection", {"image_path": image})
    r2 = g.infer("detection", {"image_path": image})
    assert "cached" not in r1 and "cached" not in r2
    cache_dir = file_cache_env / "cache"
    assert not cache_dir.exists() or not any(cache_dir.iterdir())


def test_missing_image_skips_cache_and_reaches_backend(file_cache_env, monkeypatch):
    def fake_detect(image_path, device="cuda"):
        raise FileNotFoundError(image_path)

    monkeypatch.setattr(adapters, "detect_elements", fake_detect)
    monkeypatch.delenv("HOSTED_VLM_BASE_URL", raising=False)
    monkeypatch.delenv("HOSTED_VLM_API_KEY", raising=False)
    g = InferenceGateway("local-6gb")
    with pytest.raises(Exception, match="fallback"):
        g.infer("detection", {"image_path": "does-not-exist.png"})
