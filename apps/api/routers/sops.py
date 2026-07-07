"""SOP service (design Section 5.4, TDD-11). Owner: Pushp.

Read, edit steps, versioning, and publish with review-aware gates (BR-1/BR-2).
"""
from __future__ import annotations

import copy

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.api import audit
from apps.api.security_ctx import Principal, require
from apps.api.store import store
from processiq_shared.enums import SopState
from processiq_shared.models import SOP

router = APIRouter(prefix="/v1/sops", tags=["sops"])


class StepEdit(BaseModel):
    action: str | None = None
    description: str | None = None


@router.get("/{sop_id}", response_model=SOP)
def get_sop(sop_id: str, p: Principal = Depends(require("sop:read"))) -> SOP:
    sop = store.get_sop(sop_id)
    if not sop:
        raise HTTPException(status_code=404, detail="sop not found")
    return sop


@router.get("/{sop_id}/versions")
def list_versions(sop_id: str, p: Principal = Depends(require("sop:read"))) -> dict:
    versions = store.sop_versions.get(sop_id, [])
    return {"sopId": sop_id, "versions": [{"version": v.version, "state": v.state.value,
                                           "confidence": v.overall_confidence} for v in versions]}


@router.patch("/{sop_id}/steps/{no}")
def edit_step(sop_id: str, no: int, edit: StepEdit,
              p: Principal = Depends(require("sop:edit"))) -> dict:
    sop = store.get_sop(sop_id)
    if not sop:
        raise HTTPException(status_code=404, detail="sop not found")
    step = next((s for s in sop.steps if s.no == no), None)
    if not step:
        raise HTTPException(status_code=404, detail="step not found")
    if edit.action is not None:
        step.action = edit.action
    if edit.description is not None:
        step.description = edit.description
    store.save_sop(sop)
    audit.record(sop.tenant_id, p.user, "step.edit", "sop", sop_id, {"step": no})
    return {"sopId": sop_id, "step": no, "action": step.action}


@router.post("/{sop_id}:publish")
def publish_sop(sop_id: str, p: Principal = Depends(require("sop:publish"))) -> dict:
    sop = store.get_sop(sop_id)
    if not sop:
        raise HTTPException(status_code=404, detail="sop not found")
    approved = store.reviews.get(sop_id, {}).get("approved", set())
    # Gate: any flagged step must be explicitly approved (design BR-1/BR-2).
    blocked = [s.no for s in sop.steps if s.flags and s.no not in approved]
    if blocked:
        raise HTTPException(status_code=409,
                            detail=f"cannot publish: steps need review/approval -> {blocked}")
    # Snapshot immutable version.
    store.sop_versions.setdefault(sop_id, []).append(copy.deepcopy(sop))
    sop.state = SopState.PUBLISHED
    sop.version += 1
    store.save_sop(sop)
    audit.record(sop.tenant_id, p.user, "sop.publish", "sop", sop_id, {"version": sop.version})
    return {"sopId": sop.id, "state": sop.state.value, "version": sop.version}
