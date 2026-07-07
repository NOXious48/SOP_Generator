"""Admin / tenant / RBAC / policy management (design Section 5.9, TDD-16). Owner: Utkarsh."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.api import audit
from apps.api.security_ctx import Principal, require
from apps.api.store import store

router = APIRouter(prefix="/v1", tags=["admin"])


class TenantCreate(BaseModel):
    name: str
    region: str = "primary"


class PolicyUpdate(BaseModel):
    confidence_threshold: float = 0.75
    retention_days: int = 90
    training_opt_in: bool = False


@router.post("/tenants", status_code=201)
def create_tenant(req: TenantCreate, p: Principal = Depends(require("*"))) -> dict:
    tid = store.new_id("tenant")
    store.tenants[tid] = {"id": tid, "name": req.name, "region": req.region,
                          "policy": PolicyUpdate().model_dump()}
    audit.record(p.tenant_id, p.user, "tenant.create", "tenant", tid, {"name": req.name})
    return {"tenantId": tid, "name": req.name}


@router.put("/policies")
def update_policy(req: PolicyUpdate, p: Principal = Depends(require("*"))) -> dict:
    t = store.tenants.setdefault(p.tenant_id, {"id": p.tenant_id, "name": p.tenant_id})
    t["policy"] = req.model_dump()
    audit.record(p.tenant_id, p.user, "policy.update", "tenant", p.tenant_id, req.model_dump())
    return {"tenantId": p.tenant_id, "policy": req.model_dump()}


@router.get("/policies")
def get_policy(p: Principal = Depends(require("sop:read"))) -> dict:
    t = store.tenants.get(p.tenant_id, {})
    return t.get("policy", PolicyUpdate().model_dump())


@router.get("/audit")
def get_audit(p: Principal = Depends(require("audit:read"))) -> dict:
    if not p.can("audit:read"):
        raise HTTPException(status_code=403, detail="forbidden")
    return {"entries": audit.entries(p.tenant_id), "chain_valid": audit.verify_chain()}
