"""Integration endpoints (design Section 5.8, TDD-15). Owner: Ankur2."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.api import audit
from apps.api.security_ctx import Principal, require
from apps.api.store import store
from services.integration import Connector

router = APIRouter(prefix="/v1", tags=["integrations"])

_SUPPORTED = {"confluence", "slack", "jira", "servicenow", "sharepoint", "teams"}


class IntegrationCreate(BaseModel):
    type: str
    dry_run: bool = True
    config: dict = {}


@router.post("/integrations", status_code=201)
def create_integration(req: IntegrationCreate, p: Principal = Depends(require("*"))) -> dict:
    if req.type not in _SUPPORTED:
        raise HTTPException(status_code=400, detail=f"unsupported integration '{req.type}'")
    iid = store.new_id("intg")
    store.tenants.setdefault(p.tenant_id, {"id": p.tenant_id}).setdefault("integrations", {})[iid] = {
        "id": iid, "type": req.type, "dry_run": req.dry_run, "config": req.config}
    audit.record(p.tenant_id, p.user, "integration.create", "integration", iid, {"type": req.type})
    return {"integrationId": iid, "type": req.type, "dryRun": req.dry_run}


@router.post("/sops/{sop_id}/publish-to/{target}")
def publish_to(sop_id: str, target: str, p: Principal = Depends(require("export:create"))) -> dict:
    sop = store.get_sop(sop_id)
    if not sop:
        raise HTTPException(status_code=404, detail="sop not found")
    if target not in _SUPPORTED:
        raise HTTPException(status_code=400, detail=f"unsupported target '{target}'")
    result = Connector(kind=target, dry_run=True).publish_sop(sop)
    audit.record(sop.tenant_id, p.user, "sop.publish_to", "sop", sop_id, {"target": target})
    return {"target": result.target, "ok": result.ok, "detail": result.detail,
            "dryRun": result.dry_run}
