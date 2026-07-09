"""UI-drift detection (design UJ-2, FR-022). Owner: Pushp.

Compares a fresh set of screenshots for a process against the ones a SOP was generated from, using
perceptual-hash distance per screen. Surfaces which screens changed and which SOP steps are affected
so a stale SOP can be regenerated — the "keep documentation accurate as the UI evolves" requirement.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.api.security_ctx import Principal, require
from apps.api.store import store
from services.preprocess import hamming

router = APIRouter(prefix="/v1/sops", tags=["drift"])

_CHANGE_THRESHOLD = 6   # pHash Hamming distance above which a screen is "changed"


class DriftBody(BaseModel):
    new_process_id: str   # a process holding the current/updated screenshots


def _ordered(proc: dict) -> list[dict]:
    return sorted(proc.get("artifacts", []), key=lambda a: a.get("order", 0))


@router.post("/{sop_id}/drift")
def check_drift(sop_id: str, body: DriftBody, p: Principal = Depends(require("sop:read"))) -> dict:
    sop = store.get_sop(sop_id)
    if not sop:
        raise HTTPException(status_code=404, detail="sop not found")
    old_proc = store.processes.get(sop.process_id)
    new_proc = store.processes.get(body.new_process_id)
    if not old_proc or not new_proc:
        raise HTTPException(status_code=404, detail="process not found")

    old, new = _ordered(old_proc), _ordered(new_proc)
    total = max(len(old), len(new))
    screens, changed = [], 0
    for i in range(total):
        oa = old[i] if i < len(old) else None
        na = new[i] if i < len(new) else None
        if oa and na:
            oh, nh = oa.get("phash"), na.get("phash")
            dist = hamming(oh, nh) if oh and nh else 64
            is_changed = dist > _CHANGE_THRESHOLD
            screens.append({"order": i + 1, "distance": dist, "changed": is_changed,
                            "newArtifactId": na["id"]})
        else:
            is_changed = True
            screens.append({"order": i + 1, "changed": True,
                            "note": "screen removed" if oa else "new screen"})
        if is_changed:
            changed += 1

    changed_orders = {s["order"] for s in screens if s.get("changed")}
    # a step is affected if its screenshot sits on a changed screen (steps are ordered by screen)
    affected = [s.no for s in sop.steps
                if s.screenshot_ref and _step_screen(sop, s) in changed_orders]

    return {
        "sopId": sop_id,
        "driftScore": round(changed / total, 2) if total else 0.0,
        "changedScreens": changed,
        "totalScreens": total,
        "drift": changed > 0,
        "screens": screens,
        "affectedSteps": affected,
        "newProcessId": body.new_process_id,
    }


def _step_screen(sop, step) -> int:
    """Best-effort: map a step to its 1-based screen index by its artifact's order."""
    proc = store.processes.get(sop.process_id, {})
    for a in _ordered(proc):
        if step.screenshot_ref and a["id"] == step.screenshot_ref.artifact_id:
            return a.get("order", 0)
    return step.no
