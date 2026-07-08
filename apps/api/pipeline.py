"""Glue between the control plane and the orchestrator.

In production the API only enqueues a job and a separate orchestrator worker consumes it (design
Section 8). For the scaffold we run the pipeline inline so the demo works with no broker.
"""
from __future__ import annotations

import os
from typing import Any

from apps import bus
from apps.api import objstore
from apps.api.config import settings
from apps.api.store import store
from apps.orchestrator.graph import run_pipeline, run_vlm_pipeline
from processiq_shared.enums import JobStatus
from processiq_shared.events import (
    SUBJECT_JOB_COMPLETED,
    SUBJECT_JOB_STAGE,
    Event,
)
from processiq_shared.models import JobView, ScreenPerception
from processiq_shared.state import AgentState, JobContext


def _vlm_available() -> bool:
    return bool(os.getenv("HOSTED_VLM_BASE_URL") and os.getenv("HOSTED_VLM_API_KEY"))


def run_job(job: JobView, options: dict[str, Any] | None = None) -> JobView:
    options = options or {}
    process = store.processes.get(job.process_id, {})
    artifacts = process.get("artifacts", [])
    screens = [
        ScreenPerception(artifact_id=a["id"], order=a.get("order", i + 1))
        for i, a in enumerate(artifacts)
    ]
    # Real uploads carry an object_key; hand agents the resolved paths so the models run on them.
    artifact_paths = {
        a["id"]: str(objstore.abspath(a["object_key"]))
        for a in artifacts
        if a.get("object_key") and objstore.exists(a["object_key"])
    }
    state = AgentState(
        job=JobContext(
            id=job.id,
            tenant_id=job.tenant_id,
            process_id=job.process_id,
            plan={
                "artifact_paths": artifact_paths,
                "instruction": options.get("instruction", ""),
                "process_name": process.get("name", ""),
            },
            confidence_threshold=settings.confidence_threshold,
        ),
        screens=screens,
    )

    def on_progress(stage: str, pct: int, msg: str) -> None:
        job.stage = stage
        job.progress = pct
        job.status = JobStatus.RUNNING.value
        store.append_progress(job.id, {"stage": stage, "progress": pct, "message": msg})
        store.save_job(job)
        bus.publish(Event(subject=SUBJECT_JOB_STAGE, tenant_id=job.tenant_id, job_id=job.id,
                          payload={"stage": stage, "progress": pct, "message": msg}))

    # Prefer the real VLM path when a hosted model is configured and we have screenshot files.
    use_vlm = _vlm_available() and bool(artifact_paths) and options.get("vlm", True)
    state = (run_vlm_pipeline if use_vlm else run_pipeline)(state, on_progress)

    if state.sop:
        store.save_sop(state.sop)
        job.sop_id = state.sop.id
    store.states[job.id] = state

    needs_review = state.sop is not None and any(s.flags for s in state.sop.steps)
    job.status = (JobStatus.NEEDS_REVIEW if needs_review else JobStatus.COMPLETED).value
    job.stage = "done"
    job.progress = 100
    store.save_job(job)
    bus.publish(Event(subject=SUBJECT_JOB_COMPLETED, tenant_id=job.tenant_id, job_id=job.id,
                      payload={"status": job.status, "sopId": job.sop_id,
                               "overallConfidence": state.sop.overall_confidence if state.sop else 0}))
    return job


def run_job_safe(job: JobView, options: dict[str, Any] | None = None) -> JobView:
    """Background-thread entrypoint: a crash must land in job.error, never vanish."""
    try:
        return run_job(job, options)
    except Exception as exc:  # noqa: BLE001
        job.status = JobStatus.FAILED.value
        job.stage = "failed"
        job.error = {"title": type(exc).__name__, "detail": str(exc)}
        store.save_job(job)
        store.append_progress(job.id, {"stage": "failed", "progress": job.progress,
                                       "message": str(exc)})
        return job
