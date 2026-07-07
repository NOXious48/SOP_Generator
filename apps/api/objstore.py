"""Local filesystem object store implementing the S3-style interface (design Section 9.7).

Owner: Utkarsh/Tarun. Swap for S3/MinIO by reimplementing put/get with the same signatures.
Layout: <root>/tenant/{tenantId}/process/{processId}/{kind}/{artifactId}
"""
from __future__ import annotations

import hashlib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2] / "objstore_data"


def _key(tenant: str, process_id: str, kind: str, artifact_id: str, ext: str) -> Path:
    p = _ROOT / "tenant" / tenant / "process" / process_id / kind
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{artifact_id}{ext}"


def put(tenant: str, process_id: str, kind: str, artifact_id: str, data: bytes, ext: str = ".bin") -> dict:
    path = _key(tenant, process_id, kind, artifact_id, ext)
    path.write_bytes(data)
    return {
        "object_key": str(path.relative_to(_ROOT)),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def get(object_key: str) -> bytes:
    return (_ROOT / object_key).read_bytes()


def abspath(object_key: str) -> Path:
    return _ROOT / object_key


def exists(object_key: str) -> bool:
    return (_ROOT / object_key).exists()
