"""SOP service (design Section 5.4, TDD-11). Owner: Pushp.

Read, edit/add/delete steps (each edit snapshots a new immutable version), version history, and
publish with review-aware gates (BR-1/BR-2).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.api import audit
from apps.api.security_ctx import Principal, require
from apps.api.store import store
from processiq_shared.enums import SopState
from processiq_shared.models import SOP, ScreenshotRef, SopStep

router = APIRouter(prefix="/v1/sops", tags=["sops"])


class StepEdit(BaseModel):
    action: str | None = None
    description: str | None = None


class NewStep(BaseModel):
    action: str = "New step"
    description: str = ""
    after: int | None = None            # insert after this step number (None = append)
    artifact_id: str | None = None      # optional screenshot to reference


def _require_sop(sop_id: str) -> SOP:
    sop = store.get_sop(sop_id)
    if not sop:
        raise HTTPException(status_code=404, detail="sop not found")
    return sop


def _renumber(sop: SOP) -> None:
    for i, s in enumerate(sop.steps, start=1):
        s.no = i


def _commit_edit(sop: SOP) -> None:
    """Bump the version, save the working doc, and snapshot it as a new immutable version."""
    _renumber(sop)
    sop.overall_confidence = (round(sum(s.confidence for s in sop.steps) / len(sop.steps), 3)
                              if sop.steps else 0.0)
    sop.version += 1
    store.save_sop(sop)
    store.new_version(sop)


@router.get("")
def list_sops(p: Principal = Depends(require("sop:read"))) -> dict:
    """History of generated SOPs for the tenant, newest first."""
    return {"sops": [{"id": s.id, "title": s.title, "state": s.state.value,
                      "confidence": s.overall_confidence, "steps": len(s.steps),
                      "processId": s.process_id, "createdAt": s.created_at.isoformat()}
                     for s in store.list_sops(p.tenant_id)]}


@router.get("/{sop_id}", response_model=SOP)
def get_sop(sop_id: str, p: Principal = Depends(require("sop:read"))) -> SOP:
    return _require_sop(sop_id)


@router.get("/{sop_id}/versions")
def list_versions(sop_id: str, p: Principal = Depends(require("sop:read"))) -> dict:
    return {"sopId": sop_id,
            "versions": [{"version": v.version, "state": v.state.value,
                          "confidence": v.overall_confidence, "steps": len(v.steps)}
                         for v in store.list_versions(sop_id)]}


@router.get("/{sop_id}/versions/{version}", response_model=SOP)
def get_version(sop_id: str, version: int, p: Principal = Depends(require("sop:read"))) -> SOP:
    v = store.get_version(sop_id, version)
    if not v:
        raise HTTPException(status_code=404, detail="version not found")
    return v


@router.patch("/{sop_id}/steps/{no}")
def edit_step(sop_id: str, no: int, edit: StepEdit,
              p: Principal = Depends(require("sop:edit"))) -> dict:
    sop = _require_sop(sop_id)
    step = next((s for s in sop.steps if s.no == no), None)
    if not step:
        raise HTTPException(status_code=404, detail="step not found")
    before = {"action": step.action, "description": step.description}
    if edit.action is not None:
        step.action = edit.action
    if edit.description is not None:
        step.description = edit.description
    _commit_edit(sop)
    store.add_feedback({"tenant_id": sop.tenant_id, "sop_id": sop_id, "step_no": no, "type": "edit",
                        "before": before, "after": {"action": step.action, "description": step.description},
                        "actor": p.user})
    audit.record(sop.tenant_id, p.user, "step.edit", "sop", sop_id, {"step": no})
    return {"sopId": sop_id, "version": sop.version}


@router.post("/{sop_id}/steps", status_code=201)
def add_step(sop_id: str, body: NewStep, p: Principal = Depends(require("sop:edit"))) -> dict:
    sop = _require_sop(sop_id)
    ref = ScreenshotRef(artifact_id=body.artifact_id, bbox=[0.0, 0.0, 0.0, 0.0]) if body.artifact_id else None
    step = SopStep(no=0, action=body.action, description=body.description,
                   screenshot_ref=ref, confidence=1.0)
    idx = next((i for i, s in enumerate(sop.steps) if s.no == body.after), len(sop.steps) - 1) + 1 \
        if body.after else len(sop.steps)
    sop.steps.insert(idx, step)
    _commit_edit(sop)
    store.add_feedback({"tenant_id": sop.tenant_id, "sop_id": sop_id, "type": "add",
                        "after": {"action": step.action, "description": step.description}, "actor": p.user})
    audit.record(sop.tenant_id, p.user, "step.add", "sop", sop_id, {"at": idx})
    return {"sopId": sop_id, "version": sop.version, "steps": len(sop.steps)}


@router.delete("/{sop_id}/steps/{no}")
def delete_step(sop_id: str, no: int, p: Principal = Depends(require("sop:edit"))) -> dict:
    sop = _require_sop(sop_id)
    victim = next((s for s in sop.steps if s.no == no), None)
    if not victim:
        raise HTTPException(status_code=404, detail="step not found")
    sop.steps = [s for s in sop.steps if s.no != no]
    _commit_edit(sop)
    store.add_feedback({"tenant_id": sop.tenant_id, "sop_id": sop_id, "type": "delete",
                        "before": {"action": victim.action, "description": victim.description},
                        "actor": p.user})
    audit.record(sop.tenant_id, p.user, "step.delete", "sop", sop_id, {"step": no})
    return {"sopId": sop_id, "version": sop.version, "steps": len(sop.steps)}


@router.post("/{sop_id}:publish")
def publish_sop(sop_id: str, p: Principal = Depends(require("sop:publish"))) -> dict:
    sop = _require_sop(sop_id)
    approved = store.reviews.get(sop_id, {}).get("approved", set())
    # Gate: any flagged step must be explicitly approved (design BR-1/BR-2).
    blocked = [s.no for s in sop.steps if s.flags and s.no not in approved]
    if blocked:
        raise HTTPException(status_code=409,
                            detail=f"cannot publish: steps need review/approval -> {blocked}")
    sop.state = SopState.PUBLISHED
    sop.version += 1
    store.save_sop(sop)
    store.new_version(sop)   # published state is an immutable version
    audit.record(sop.tenant_id, p.user, "sop.publish", "sop", sop_id, {"version": sop.version})
    return {"sopId": sop.id, "state": sop.state.value, "version": sop.version}
