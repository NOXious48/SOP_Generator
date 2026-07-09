"""Store for the control plane.

In-memory dicts for speed + a JSON snapshot on disk so data survives restarts (design Section 9
defines the eventual Postgres/Mongo schema; this is the pragmatic local persistence).

Durable (saved to disk): processes, sops, sop_versions, reviews.
Transient (per-run, in-memory only): jobs, states, progress.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from processiq_shared.models import SOP, JobView
from processiq_shared.state import AgentState

_DB = Path(os.getenv("DATA_DIR", "data")) / "store.json"


class InMemoryStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.tenants: dict[str, dict] = {}
        self.processes: dict[str, dict] = {}
        self.jobs: dict[str, JobView] = {}
        self.sops: dict[str, SOP] = {}
        self.sop_versions: dict[str, list[SOP]] = {}
        self.states: dict[str, AgentState] = {}
        self.progress: dict[str, list[dict]] = {}
        self.reviews: dict[str, dict] = {}
        self.feedback: list[dict] = []   # correction/learning memory (durable)
        self.chats: dict[str, list[dict]] = {}   # per-SOP chat history (durable)
        self._load()

    @staticmethod
    def new_id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex[:24]}"

    # ---------- persistence ----------
    def persist(self) -> None:
        """Snapshot the durable entities to disk (atomic write)."""
        with self._lock:
            data = {
                "processes": self.processes,
                "sops": {k: v.model_dump(mode="json") for k, v in self.sops.items()},
                "sop_versions": {k: [s.model_dump(mode="json") for s in vs]
                                 for k, vs in self.sop_versions.items()},
                "reviews": {k: {"approved": sorted(v.get("approved", set())),
                                "log": v.get("log", [])} for k, v in self.reviews.items()},
                "feedback": self.feedback,
                "chats": self.chats,
            }
            _DB.parent.mkdir(parents=True, exist_ok=True)
            tmp = _DB.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(_DB)  # atomic

    def _load(self) -> None:
        if not _DB.exists():
            return
        try:
            data = json.loads(_DB.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - corrupt snapshot must not crash startup
            return
        self.processes = data.get("processes", {})
        self.sops = {k: SOP.model_validate(v) for k, v in data.get("sops", {}).items()}
        self.sop_versions = {k: [SOP.model_validate(s) for s in vs]
                             for k, vs in data.get("sop_versions", {}).items()}
        self.reviews = {k: {"approved": set(v.get("approved", [])), "log": v.get("log", [])}
                        for k, v in data.get("reviews", {}).items()}
        self.feedback = data.get("feedback", [])
        self.chats = data.get("chats", {})

    # ---------- processes ----------
    def create_process(self, tenant_id: str, name: str) -> str:
        with self._lock:
            pid = self.new_id("proc")
            self.processes[pid] = {"id": pid, "tenant_id": tenant_id, "name": name,
                                   "artifacts": [], "created_at": datetime.now(UTC).isoformat()}
        self.persist()
        return pid

    def add_artifact(self, process_id: str, artifact: dict) -> None:
        with self._lock:
            self.processes[process_id]["artifacts"].append(artifact)
        self.persist()

    def list_processes(self, tenant_id: str) -> list[dict]:
        return sorted((p for p in self.processes.values() if p.get("tenant_id") == tenant_id),
                      key=lambda p: p.get("created_at", ""), reverse=True)

    # ---------- jobs (transient) ----------
    def save_job(self, job: JobView) -> None:
        with self._lock:
            self.jobs[job.id] = job

    def get_job(self, job_id: str) -> JobView | None:
        return self.jobs.get(job_id)

    # ---------- sops ----------
    def save_sop(self, sop: SOP) -> None:
        with self._lock:
            self.sops[sop.id] = sop
        self.persist()

    def get_sop(self, sop_id: str) -> SOP | None:
        return self.sops.get(sop_id)

    def list_sops(self, tenant_id: str) -> list[SOP]:
        return sorted((s for s in self.sops.values() if s.tenant_id == tenant_id),
                      key=lambda s: s.created_at, reverse=True)

    def add_version(self, sop_id: str, snapshot: SOP) -> None:
        with self._lock:
            self.sop_versions.setdefault(sop_id, []).append(snapshot)
        self.persist()

    def new_version(self, sop: SOP) -> None:
        """Snapshot the working SOP as an immutable version (its .version = version number)."""
        with self._lock:
            self.sop_versions.setdefault(sop.id, []).append(sop.model_copy(deep=True))
        self.persist()

    def get_version(self, sop_id: str, version: int) -> SOP | None:
        return next((v for v in self.sop_versions.get(sop_id, []) if v.version == version), None)

    def list_versions(self, sop_id: str) -> list[SOP]:
        return self.sop_versions.get(sop_id, [])

    # ---------- feedback / learning memory ----------
    def add_feedback(self, record: dict) -> None:
        with self._lock:
            record.setdefault("id", self.new_id("fb"))
            record.setdefault("at", datetime.now(UTC).isoformat())
            self.feedback.append(record)
        self.persist()

    def list_feedback(self, tenant_id: str, limit: int | None = None) -> list[dict]:
        items = [f for f in self.feedback if f.get("tenant_id") == tenant_id]
        items = sorted(items, key=lambda f: f.get("at", ""), reverse=True)
        return items[:limit] if limit else items

    # ---------- chat (per-SOP conversation, durable) ----------
    def add_chat(self, sop_id: str, role: str, text: str) -> dict:
        msg = {"role": role, "text": text, "at": datetime.now(UTC).isoformat()}
        with self._lock:
            self.chats.setdefault(sop_id, []).append(msg)
        self.persist()
        return msg

    def get_chat(self, sop_id: str) -> list[dict]:
        return self.chats.get(sop_id, [])

    # ---------- progress (transient) ----------
    def append_progress(self, job_id: str, event: dict) -> None:
        with self._lock:
            self.progress.setdefault(job_id, []).append(event)

    def get_progress(self, job_id: str) -> list[dict]:
        return self.progress.get(job_id, [])


store = InMemoryStore()
