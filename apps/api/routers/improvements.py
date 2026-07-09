"""Improvement suggestions (user-submitted, admin-curated).

The role-based improvement loop (design Section 5.12 extension):
  * Any reader (Viewer+) can submit an improvement suggestion against a whole SOP or a single step.
  * Admins (feedback:manage) read the inbox, edit/curate the wording, mark items resolved/dismissed,
    and turn the accepted suggestions into an instruction that regenerates an improved SOP version
    (via the existing refine pipeline — the client fires the refine job and marks items resolved).

Suggestions are persisted as feedback records with type="suggestion" so they survive restarts and
also feed the learning memory. Owner: Pushp.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.api import audit
from apps.api.security_ctx import Principal, require
from apps.api.store import store

router = APIRouter(prefix="/v1/sops", tags=["improvements"])

_OPEN = "open"
_STATUSES = {"open", "resolved", "dismissed"}


class SuggestionBody(BaseModel):
    comment: str
    step_no: int | None = None          # None = applies to the whole SOP


class SuggestionPatch(BaseModel):
    edited_comment: str | None = None   # admin curation of the wording
    status: str | None = None           # open | resolved | dismissed
    resolved_version: int | None = None # SOP version produced from this suggestion


def _sop_or_404(sop_id: str):
    sop = store.get_sop(sop_id)
    if not sop:
        raise HTTPException(status_code=404, detail="sop not found")
    return sop


def _view(f: dict) -> dict:
    """Public shape of a suggestion record."""
    return {
        "id": f.get("id"),
        "sopId": f.get("sop_id"),
        "stepNo": f.get("step_no"),
        "comment": f.get("comment", ""),
        "editedComment": f.get("edited_comment"),
        "effective": f.get("edited_comment") or f.get("comment", ""),
        "status": f.get("status", _OPEN),
        "author": f.get("actor"),
        "at": f.get("at"),
        "resolvedBy": f.get("resolved_by"),
        "resolvedVersion": f.get("resolved_version"),
    }


@router.post("/{sop_id}/suggestions", status_code=201)
def submit_suggestion(sop_id: str, body: SuggestionBody,
                      p: Principal = Depends(require("sop:suggest"))) -> dict:
    """A reader proposes an improvement for the whole SOP or a specific step."""
    sop = _sop_or_404(sop_id)
    comment = body.comment.strip()
    if not comment:
        raise HTTPException(status_code=422, detail="comment is required")
    if body.step_no is not None and not any(s.no == body.step_no for s in sop.steps):
        raise HTTPException(status_code=404, detail=f"step {body.step_no} not found")
    rec = {"tenant_id": sop.tenant_id, "sop_id": sop_id, "step_no": body.step_no,
           "type": "suggestion", "status": _OPEN, "comment": comment, "actor": p.user}
    store.add_feedback(rec)
    audit.record(sop.tenant_id, p.user, "suggestion.submit", "sop", sop_id,
                 {"step": body.step_no})
    return _view(rec)


@router.get("/{sop_id}/suggestions")
def list_suggestions(sop_id: str, p: Principal = Depends(require("sop:read"))) -> dict:
    """List improvement suggestions for a SOP (newest first)."""
    _sop_or_404(sop_id)
    items = [_view(f) for f in store.list_suggestions(p.tenant_id, sop_id)]
    return {"sopId": sop_id, "suggestions": items,
            "open": sum(1 for i in items if i["status"] == _OPEN)}


@router.patch("/{sop_id}/suggestions/{sid}")
def curate_suggestion(sop_id: str, sid: str, patch: SuggestionPatch,
                      p: Principal = Depends(require("feedback:manage"))) -> dict:
    """Admin edits the wording and/or resolves/dismisses a suggestion."""
    _sop_or_404(sop_id)
    rec = store.get_feedback(sid)
    if not rec or rec.get("type") != "suggestion" or rec.get("sop_id") != sop_id:
        raise HTTPException(status_code=404, detail="suggestion not found")
    updates: dict = {}
    if patch.edited_comment is not None:
        updates["edited_comment"] = patch.edited_comment.strip()
    if patch.status is not None:
        if patch.status not in _STATUSES:
            raise HTTPException(status_code=422, detail=f"status must be one of {sorted(_STATUSES)}")
        updates["status"] = patch.status
        if patch.status in ("resolved", "dismissed"):
            updates["resolved_by"] = p.user
    if patch.resolved_version is not None:
        updates["resolved_version"] = patch.resolved_version
    rec = store.update_feedback(sid, updates)
    audit.record(rec["tenant_id"], p.user, "suggestion.curate", "sop", sop_id,
                 {"suggestion": sid, **{k: v for k, v in updates.items() if k != "resolved_by"}})
    return _view(rec)
