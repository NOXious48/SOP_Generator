"""Export endpoints (design Section 5.7, TDD-14). Owner: Ankur2."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from apps.api import audit
from apps.api.security_ctx import Principal, require
from apps.api.store import store
from services.export import SUPPORTED, export

router = APIRouter(prefix="/v1/sops", tags=["exports"])


class ExportRequest(BaseModel):
    format: str = "markdown"


@router.get("/{sop_id}/exports/formats")
def list_formats(p: Principal = Depends(require("sop:read"))) -> dict:
    return {"formats": sorted(SUPPORTED)}


@router.post("/{sop_id}/exports")
def create_export(sop_id: str, req: ExportRequest,
                  p: Principal = Depends(require("export:create"))) -> Response:
    sop = store.get_sop(sop_id)
    if not sop:
        raise HTTPException(status_code=404, detail="sop not found")
    try:
        data, content_type = export(sop, req.format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit.record(sop.tenant_id, p.user, "sop.export", "sop", sop_id, {"format": req.format})
    ext = req.format.lower().replace("markdown", "md")
    return Response(content=data, media_type=content_type,
                    headers={"Content-Disposition": f"attachment; filename={sop_id}.{ext}"})
