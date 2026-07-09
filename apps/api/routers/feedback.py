"""Feedback / learning-memory endpoints (design Section 5.12, FR-110).

Captures explicit user feedback and exposes the accumulated correction memory that is fed back into
future SOP generation (see apps/api/pipeline.py -> learned guidance).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.api import audit
from apps.api.security_ctx import Principal, require
from apps.api.store import store

router = APIRouter(prefix="/v1/feedback", tags=["feedback"])


class FeedbackBody(BaseModel):
    sop_id: str | None = None
    rating: str | None = None          # "up" | "down"
    comment: str = ""
    step_no: int | None = None


@router.post("", status_code=201)
def submit_feedback(body: FeedbackBody, p: Principal = Depends(require("sop:read"))) -> dict:
    store.add_feedback({"tenant_id": p.tenant_id, "sop_id": body.sop_id, "step_no": body.step_no,
                        "type": "rating", "rating": body.rating, "comment": body.comment,
                        "actor": p.user})
    audit.record(p.tenant_id, p.user, "feedback.submit", "sop", body.sop_id or "-",
                 {"rating": body.rating})
    return {"ok": True}


@router.get("")
def list_feedback(p: Principal = Depends(require("sop:read"))) -> dict:
    items = store.list_feedback(p.tenant_id)
    corrections = [f for f in items if f.get("type") in ("edit", "add", "delete")]
    return {
        "total": len(items),
        "corrections": len(corrections),   # how much the system has learned
        "up": sum(1 for f in items if f.get("rating") == "up"),
        "down": sum(1 for f in items if f.get("rating") == "down"),
        "recent": items[:20],
    }
