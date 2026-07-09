"""Export endpoints (design Section 5.7, TDD-14). Owner: Ankur2."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from apps.api import audit, objstore
from apps.api.security_ctx import Principal, require
from apps.api.store import store
from services.export import SUPPORTED, export

router = APIRouter(prefix="/v1/sops", tags=["exports"])


def _image_loader_for(process_id: str):
    """Resolve a step's artifact_id -> stored screenshot bytes, so exports can embed them."""
    proc = store.processes.get(process_id, {})
    keys = {a["id"]: a.get("object_key") for a in proc.get("artifacts", [])}

    def load(artifact_id: str) -> bytes | None:
        key = keys.get(artifact_id)
        if key and objstore.exists(key):
            return objstore.get(key)
        return None

    return load


class ExportRequest(BaseModel):
    format: str = "markdown"
    version: int | None = None   # export a specific version; None = current working SOP


@router.get("/{sop_id}/exports/formats")
def list_formats(p: Principal = Depends(require("sop:read"))) -> dict:
    return {"formats": sorted(SUPPORTED)}


@router.post("/{sop_id}/exports")
def create_export(sop_id: str, req: ExportRequest,
                  p: Principal = Depends(require("export:create"))) -> Response:
    sop = store.get_version(sop_id, req.version) if req.version else store.get_sop(sop_id)
    if not sop:
        raise HTTPException(status_code=404, detail="sop/version not found")
    try:
        data, content_type = export(sop, req.format, image_loader=_image_loader_for(sop.process_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit.record(sop.tenant_id, p.user, "sop.export", "sop", sop_id,
                 {"format": req.format, "version": req.version})
    ext = req.format.lower().replace("markdown", "md")
    suffix = f"_v{req.version}" if req.version else ""
    return Response(content=data, media_type=content_type,
                    headers={"Content-Disposition": f"attachment; filename={sop_id}{suffix}.{ext}"})
