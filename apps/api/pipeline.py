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
from processiq_shared.enums import JobStatus, SopState
from processiq_shared.events import (
    SUBJECT_JOB_COMPLETED,
    SUBJECT_JOB_STAGE,
    Event,
)
from processiq_shared.models import JobView, ScreenPerception
from processiq_shared.state import AgentState, JobContext


def _vlm_available() -> bool:
    return bool(os.getenv("HOSTED_VLM_BASE_URL") and os.getenv("HOSTED_VLM_API_KEY"))


def _learned_guidance(tenant_id: str) -> str:
    """Turn accumulated corrections + an approved exemplar into prompt guidance, so generation
    visibly improves from feedback (design §6.9 exemplar/prompt-tuning, the cheap-wins-first path)."""
    parts: list[str] = []
    edits = [f for f in store.list_feedback(tenant_id, limit=12) if f.get("type") == "edit"]
    lines: list[str] = []
    for f in edits[:6]:
        b, a = f.get("before", {}), f.get("after", {})
        if b.get("action") and a.get("action") and b["action"] != a["action"]:
            lines.append(f"- rename '{b['action']}' -> '{a['action']}'")
    if lines:
        parts.append("The user has previously corrected step wording like:\n" + "\n".join(lines)
                     + "\nApply the same naming/wording preferences.")
    approved = [s for s in store.list_sops(tenant_id)
                if s.state.value in ("PUBLISHED", "APPROVED") and s.steps]
    if approved:
        ex = approved[0]
        sample = "; ".join(f"{st.no}. {st.action}" for st in ex.steps[:4])
        parts.append(f"An approved SOP the team liked ('{ex.title}') was written as: {sample}. "
                     "Match that structure and level of detail.")
    return "\n\n".join(parts)


def _refine_instruction(sop, original: str, changes: str) -> str:
    """Combine the original request + the current SOP + the new change request into one prompt,
    so regeneration keeps everything good and applies the requested improvements."""
    steps = "\n".join(f"{s.no}. {s.action}: {s.description}" for s in sop.steps)
    orig = f"Original request: {original}\n\n" if original else ""
    return (f"{orig}You previously generated this SOP titled '{sop.title}'.\n"
            f"Objective: {sop.objective}\nSteps:\n{steps}\n\n"
            f"The user now requests these changes / improvements:\n{changes}\n\n"
            "Regenerate an improved SOP that incorporates the requested changes while keeping the "
            "rest accurate to the screenshots. Re-derive every step from the screenshots.")


def run_job(job: JobView, options: dict[str, Any] | None = None) -> JobView:
    options = options or {}
    process = store.processes.get(job.process_id, {})
    refine_id = options.get("refine_sop_id")
    existing = store.get_sop(refine_id) if refine_id else None
    if existing:
        instruction = _refine_instruction(existing, process.get("instruction", ""),
                                          options.get("instruction", ""))
    else:
        instruction = options.get("instruction", "")
        if process:                       # remember the original request for future refinements
            process["instruction"] = instruction
            store.persist()
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
                "instruction": instruction,
                "process_name": process.get("name", ""),
                "learned_guidance": _learned_guidance(job.tenant_id),
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

    if state.sop and existing:
        # Refine: the current state is already the latest saved version, so just replace the working
        # doc's content in place (same id) with the regenerated one and snapshot it as a new version.
        new = state.sop
        existing.title = new.title
        existing.objective = new.objective
        existing.prerequisites = new.prerequisites
        existing.steps = new.steps
        existing.exceptions = new.exceptions
        existing.validation = new.validation
        existing.output = new.output
        existing.overall_confidence = new.overall_confidence
        existing.process_id = job.process_id   # regenerating from updated screenshots repoints the SOP
        existing.state = SopState.DRAFT
        existing.version += 1
        store.save_sop(existing)
        store.new_version(existing)
        store.add_feedback({"tenant_id": job.tenant_id, "sop_id": existing.id, "type": "refine",
                            "after": {"instruction": options.get("instruction", "")}, "actor": "user"})
        job.sop_id = existing.id
        state.sop = existing
    elif state.sop:
        store.save_sop(state.sop)
        store.new_version(state.sop)   # record the generated SOP as version 1
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
