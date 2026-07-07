"""In-memory store for the scaffold (design Section 9 defines the real Postgres/Mongo schema).

This lets the control plane run with zero external dependencies. Owner (Utkarsh): replace with
SQLAlchemy/Postgres repositories + Mongo document store, preserving these method signatures.
"""
from __future__ import annotations

import threading
from uuid import uuid4

from processiq_shared.models import SOP, JobView
from processiq_shared.state import AgentState


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
        self.reviews: dict[str, list[dict]] = {}

    @staticmethod
    def new_id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex[:24]}"

    def create_process(self, tenant_id: str, name: str) -> str:
        with self._lock:
            pid = self.new_id("proc")
            self.processes[pid] = {"id": pid, "tenant_id": tenant_id, "name": name, "artifacts": []}
            return pid

    def add_artifact(self, process_id: str, artifact: dict) -> None:
        with self._lock:
            self.processes[process_id]["artifacts"].append(artifact)

    def save_job(self, job: JobView) -> None:
        with self._lock:
            self.jobs[job.id] = job

    def get_job(self, job_id: str) -> JobView | None:
        return self.jobs.get(job_id)

    def save_sop(self, sop: SOP) -> None:
        with self._lock:
            self.sops[sop.id] = sop

    def get_sop(self, sop_id: str) -> SOP | None:
        return self.sops.get(sop_id)

    def append_progress(self, job_id: str, event: dict) -> None:
        with self._lock:
            self.progress.setdefault(job_id, []).append(event)

    def get_progress(self, job_id: str) -> list[dict]:
        return self.progress.get(job_id, [])


store = InMemoryStore()
