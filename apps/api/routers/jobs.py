from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException

from apps.api import audit
from apps.api.metrics import JOBS
from apps.api.pipeline import run_job, run_job_safe
from apps.api.security_ctx import Principal, require
from apps.api.store import store
from processiq_shared.enums import JobStatus
from processiq_shared.models import CreateJobRequest, JobView

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


@router.post("", status_code=202)
def create_job(req: CreateJobRequest, p: Principal = Depends(require("job:create"))) -> dict:
    proc = store.processes.get(req.process_id)
    if not proc:
        raise HTTPException(status_code=404, detail="process not found")
    job = JobView(
        id=store.new_id("job"),
        tenant_id=proc["tenant_id"],
        process_id=req.process_id,
        status=JobStatus.QUEUED.value,
        stage="ingested",
        progress=0,
    )
    store.save_job(job)
    audit.record(job.tenant_id, p.user, "job.run", "job", job.id, {})
    if req.options.get("async"):
        # Real-model runs take minutes; return immediately and let the UI poll progress.
        threading.Thread(target=run_job_safe, args=(job,), daemon=True).start()
        return {"jobId": job.id, "status": job.status}
    # Scaffold default: run inline (tests/demo). Production: enqueue jobs.submitted (design §8).
    job = run_job(job)
    JOBS.labels(job.status).inc()
    return {"jobId": job.id, "status": job.status, "sopId": job.sop_id}


@router.get("/{job_id}")
def get_job(job_id: str, p: Principal = Depends(require("sop:read"))) -> JobView:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.get("/{job_id}/progress")
def get_progress(job_id: str, p: Principal = Depends(require("sop:read"))) -> dict:
    if not store.get_job(job_id):
        raise HTTPException(status_code=404, detail="job not found")
    return {"jobId": job_id, "events": store.get_progress(job_id)}


@router.get("/{job_id}/perception")
def get_perception(job_id: str, p: Principal = Depends(require("sop:read"))) -> dict:
    """Per-screen perception results (elements + text) for UI overlays."""
    state = store.states.get(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="no perception for this job (still running?)")
    return {"jobId": job_id, "screens": [s.model_dump() for s in state.screens]}


@router.get("/{job_id}/trace")
def get_trace(job_id: str, p: Principal = Depends(require("sop:read"))) -> dict:
    """Agent execution trace (design NFR-055) — which model ran, how long, status."""
    state = store.states.get(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="no trace for this job (still running?)")
    return {"jobId": job_id, "events": [t.model_dump() for t in state.trace]}
