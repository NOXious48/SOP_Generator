"""Append-only audit log (design Sections 14.7, NFR-060). Owner: Chesta.

In-memory, append-only for the scaffold; swap for the partitioned Postgres `audit_log` table.
Entries are hash-chained for tamper-evidence.
"""
from __future__ import annotations

import hashlib
import threading
from datetime import UTC, datetime
from typing import Any

_lock = threading.RLock()
_log: list[dict[str, Any]] = []


def record(tenant_id: str, actor: str, action: str, target_type: str = "", target_id: str = "",
           detail: dict | None = None) -> dict:
    with _lock:
        prev_hash = _log[-1]["hash"] if _log else "genesis"
        entry = {
            "seq": len(_log) + 1,
            "tenant_id": tenant_id,
            "actor": actor,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "detail": detail or {},
            "at": datetime.now(UTC).isoformat(),
            "prev_hash": prev_hash,
        }
        entry["hash"] = hashlib.sha256(
            f"{prev_hash}|{entry['seq']}|{action}|{target_id}|{entry['at']}".encode()
        ).hexdigest()
        _log.append(entry)
        return entry


def entries(tenant_id: str | None = None) -> list[dict]:
    with _lock:
        if tenant_id is None:
            return list(_log)
        return [e for e in _log if e["tenant_id"] == tenant_id]


def verify_chain() -> bool:
    prev = "genesis"
    for e in _log:
        expected = hashlib.sha256(
            f"{prev}|{e['seq']}|{e['action']}|{e['target_id']}|{e['at']}".encode()
        ).hexdigest()
        if expected != e["hash"]:
            return False
        prev = e["hash"]
    return True
