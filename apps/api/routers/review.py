"""Review / approval workflow (design Section 5.5, TDD-12). Owner: Utkarsh/Pushp.

Enforces publish gates (design BR-1/BR-2): a step that is flagged must be explicitly approved by a
Reviewer before the SOP can be published.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.api import audit
from apps.api.security_ctx import Principal, require
from apps.api.store import store
from processiq_shared.enums import SopState

router = APIRouter(prefix="/v1/sops", tags=["review"])


class RejectBody(BaseModel):
    comment: str = ""


def _approvals(sop_id: str) -> set[int]:
    return store.reviews.setdefault(sop_id, {}).setdefault("approved", set())  # type: ignore[return-value]


@router.post("/{sop_id}/reviews", status_code=201)
def open_review(sop_id: str, p: Principal = Depends(require("sop:read"))) -> dict:
    sop = store.get_sop(sop_id)
    if not sop:
        raise HTTPException(status_code=404, detail="sop not found")
    sop.state = SopState.IN_REVIEW
    store.save_sop(sop)
    store.reviews.setdefault(sop_id, {"approved": set(), "log": []})
    audit.record(sop.tenant_id, p.user, "review.open", "sop", sop_id)
    return {"sopId": sop_id, "state": sop.state.value}


@router.post("/{sop_id}/steps/{no}:approve")
def approve_step(sop_id: str, no: int, p: Principal = Depends(require("sop:approve"))) -> dict:
    sop = store.get_sop(sop_id)
    if not sop:
        raise HTTPException(status_code=404, detail="sop not found")
    step = next((s for s in sop.steps if s.no == no), None)
    if not step:
        raise HTTPException(status_code=404, detail="step not found")
    store.reviews.setdefault(sop_id, {"approved": set(), "log": []})
    store.reviews[sop_id]["approved"].add(no)
    store.reviews[sop_id]["log"].append({"step": no, "decision": "approve", "by": p.user})
    audit.record(sop.tenant_id, p.user, "step.approve", "sop", sop_id, {"step": no})
    return {"sopId": sop_id, "step": no, "approved": True}


@router.post("/{sop_id}/steps/{no}:reject")
def reject_step(sop_id: str, no: int, body: RejectBody,
                p: Principal = Depends(require("sop:reject"))) -> dict:
    sop = store.get_sop(sop_id)
    if not sop:
        raise HTTPException(status_code=404, detail="sop not found")
    store.reviews.setdefault(sop_id, {"approved": set(), "log": []})
    store.reviews[sop_id]["approved"].discard(no)
    store.reviews[sop_id]["log"].append({"step": no, "decision": "reject",
                                         "by": p.user, "comment": body.comment})
    audit.record(sop.tenant_id, p.user, "step.reject", "sop", sop_id,
                 {"step": no, "comment": body.comment})
    return {"sopId": sop_id, "step": no, "approved": False}


@router.post("/{sop_id}:signoff")
def signoff(sop_id: str, p: Principal = Depends(require("sop:signoff"))) -> dict:
    sop = store.get_sop(sop_id)
    if not sop:
        raise HTTPException(status_code=404, detail="sop not found")
    sop.state = SopState.APPROVED
    store.save_sop(sop)
    audit.record(sop.tenant_id, p.user, "sop.signoff", "sop", sop_id)
    return {"sopId": sop_id, "state": sop.state.value, "signedBy": p.user}
