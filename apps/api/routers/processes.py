"""Ingestion / Processes (design Section 5.1, TDD-01). Owner: Utkarsh.

Supports metadata registration (used by tests/demo) and real multipart file upload with validation,
preprocessing (Pillow), perceptual-hash de-duplication, and object-store persistence.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile

from apps.api import audit, objstore
from apps.api.security_ctx import Principal, require
from apps.api.store import store
from processiq_shared.models import CreateProcessRequest
from services.preprocess import is_duplicate, preprocess_image

router = APIRouter(prefix="/v1/processes", tags=["processes"])

ALLOWED_MIME_PREFIX = ("image/",)
MAX_BYTES = 15 * 1024 * 1024  # 15 MB per file


@router.post("", status_code=201)
def create_process(req: CreateProcessRequest, p: Principal = Depends(require("process:create"))) -> dict:
    tenant = req.tenant_id or p.tenant_id
    pid = store.create_process(tenant, req.name)
    audit.record(tenant, p.user, "process.create", "process", pid, {"name": req.name})
    return {"processId": pid, "tenantId": tenant, "name": req.name}


@router.post("/{process_id}/uploads")
def register_upload(process_id: str, filename: str, order: int | None = None,
                    p: Principal = Depends(require("job:create"))) -> dict:
    """Metadata-only registration (no bytes) — used for tests/demo and pre-signed flows."""
    proc = store.processes.get(process_id)
    if not proc:
        raise HTTPException(status_code=404, detail="process not found")
    artifact_id = store.new_id("art")
    order = order or (len(proc["artifacts"]) + 1)
    store.add_artifact(process_id, {"id": artifact_id, "filename": filename, "order": order})
    return {"artifactId": artifact_id, "order": order}


@router.post("/{process_id}/uploads:file")
async def upload_file(process_id: str, file: UploadFile,
                      p: Principal = Depends(require("job:create"))) -> dict:
    """Real file upload: validate -> preprocess -> dedup -> store."""
    proc = store.processes.get(process_id)
    if not proc:
        raise HTTPException(status_code=404, detail="process not found")
    if not (file.content_type or "").startswith(ALLOWED_MIME_PREFIX):
        raise HTTPException(status_code=415, detail=f"unsupported type: {file.content_type}")
    raw = await file.read()
    if len(raw) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="file too large")
    try:
        processed = preprocess_image(raw)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"invalid image: {exc}") from exc

    existing_hashes = [a.get("phash") for a in proc["artifacts"] if a.get("phash")]
    if is_duplicate(processed.phash, existing_hashes):
        return {"deduplicated": True, "phash": processed.phash}

    artifact_id = store.new_id("art")
    meta = objstore.put(proc["tenant_id"], process_id, "processed", artifact_id,
                        processed.data, ".png")
    order = len(proc["artifacts"]) + 1
    store.add_artifact(process_id, {
        "id": artifact_id, "filename": file.filename, "order": order,
        "phash": processed.phash, "object_key": meta["object_key"], "sha256": meta["sha256"],
        "width": processed.width, "height": processed.height,
    })
    audit.record(proc["tenant_id"], p.user, "artifact.upload", "artifact", artifact_id,
                 {"filename": file.filename})
    return {"artifactId": artifact_id, "order": order, "phash": processed.phash,
            "objectKey": meta["object_key"]}


@router.get("/{process_id}")
def get_process(process_id: str, p: Principal = Depends(require("sop:read"))) -> dict:
    proc = store.processes.get(process_id)
    if not proc:
        raise HTTPException(status_code=404, detail="process not found")
    return proc


@router.get("/{process_id}/artifacts/{artifact_id}/image")
def get_artifact_image(process_id: str, artifact_id: str,
                       p: Principal = Depends(require("sop:read"))) -> Response:
    """Serve the processed screenshot so the UI can render overlays against it."""
    proc = store.processes.get(process_id)
    if not proc:
        raise HTTPException(status_code=404, detail="process not found")
    artifact = next((a for a in proc["artifacts"] if a["id"] == artifact_id), None)
    if not artifact or not artifact.get("object_key"):
        raise HTTPException(status_code=404, detail="artifact has no stored image")
    if not objstore.exists(artifact["object_key"]):
        raise HTTPException(status_code=404, detail="image missing from object store")
    return Response(content=objstore.get(artifact["object_key"]), media_type="image/png")
