"""Auth + RBAC context (design Section 14.2). Owners: Utkarsh (RBAC), Chesta (policy).

Scaffold auth: identity is carried in headers (X-Tenant, X-User, X-Roles) simulating the JWT claims
an SSO/OIDC gateway would inject. Production replaces `principal` with real JWT validation, but the
RBAC checks and tenant scoping below stay identical.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from processiq_shared.enums import Role

# Role -> permitted actions (design Section 14.2).
PERMISSIONS: dict[Role, set[str]] = {
    Role.ADMIN: {"*"},
    Role.ANALYST: {"process:create", "job:create", "sop:read", "sop:edit", "sop:submit",
                   "export:create", "sop:suggest"},
    Role.REVIEWER: {"sop:read", "sop:approve", "sop:reject", "sop:signoff", "sop:publish", "sop:suggest"},
    Role.VIEWER: {"sop:read", "search:read", "sop:suggest", "export:create"},
    Role.AUDITOR: {"sop:read", "audit:read", "search:read"},
}
# Note: "feedback:manage" (read/curate/resolve improvement suggestions, trigger an improved version)
# is intentionally granted to Admin only — it is covered by the "*" wildcard above.


@dataclass
class Principal:
    tenant_id: str
    user: str
    roles: list[Role]

    def can(self, action: str) -> bool:
        for role in self.roles:
            perms = PERMISSIONS.get(role, set())
            if "*" in perms or action in perms:
                return True
        return False


def get_principal(
    x_tenant: str = Header(default="demo"),
    x_user: str = Header(default="analyst@demo"),
    x_roles: str = Header(default="Analyst"),
) -> Principal:
    roles: list[Role] = []
    for r in x_roles.split(","):
        r = r.strip()
        try:
            roles.append(Role(r))
        except ValueError:
            continue
    if not roles:
        roles = [Role.VIEWER]
    return Principal(tenant_id=x_tenant, user=x_user, roles=roles)


def require(action: str):
    """FastAPI dependency enforcing an RBAC action."""

    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.can(action):
            raise HTTPException(status_code=403, detail=f"role lacks permission '{action}'")
        return principal

    return _dep
