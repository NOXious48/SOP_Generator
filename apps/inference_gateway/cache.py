"""Inference result cache keyed by sha256(image) (design Sections 12.4, NFR-082).

On a single shared GPU the perception cache is the effective throughput multiplier, and with the
demo dataset pre-warmed it is also the offline-demo safety net (Section 15.7 rule 1).

Backends, in order:
- Redis when REDIS_URL is set and reachable (prod path: `perc:{...}` keys, TTL)
- JSON file cache under INFERENCE_CACHE_DIR (default `.cache/inference`) — zero services needed,
  survives restarts

Both honor the same TTL. Failures degrade to a miss; the cache never breaks inference.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

DEFAULT_TTL_S = 24 * 3600
_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class InferenceCache:
    def __init__(self, ttl_s: int = DEFAULT_TTL_S) -> None:
        self.ttl_s = ttl_s
        self._redis: Any = None
        self._redis_checked = False

    # ---------- public ----------
    def get(self, key: str) -> dict[str, Any] | None:
        r = self._get_redis()
        if r is not None:
            try:
                raw = r.get(key)
                return json.loads(raw) if raw else None
            except Exception:
                return None
        return self._file_get(key)

    def set(self, key: str, value: dict[str, Any]) -> None:
        raw = json.dumps(value)
        r = self._get_redis()
        if r is not None:
            try:
                r.setex(key, self.ttl_s, raw)
                return
            except Exception:
                pass
        self._file_set(key, raw)

    # ---------- redis backend ----------
    def _get_redis(self) -> Any:
        if self._redis_checked:
            return self._redis
        self._redis_checked = True
        url = os.getenv("REDIS_URL")
        if not url:
            return None
        try:  # pragma: no cover - needs a live redis
            import redis

            client = redis.Redis.from_url(url, socket_connect_timeout=2)
            client.ping()
            self._redis = client
        except Exception:
            self._redis = None
        return self._redis

    # ---------- file backend ----------
    def _dir(self) -> Path:
        d = Path(os.getenv("INFERENCE_CACHE_DIR", ".cache/inference"))
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _path(self, key: str) -> Path:
        return self._dir() / f"{_SAFE.sub('_', key)}.json"

    def _file_get(self, key: str) -> dict[str, Any] | None:
        p = self._path(key)
        try:
            if not p.is_file() or (time.time() - p.stat().st_mtime) > self.ttl_s:
                return None
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _file_set(self, key: str, raw: str) -> None:
        try:
            self._path(key).write_text(raw, encoding="utf-8")
        except Exception:
            pass  # cache write failure must never fail inference


cache = InferenceCache()
