"""Integration service (design Section 5.8, TDD-15). Owner: Ankur2.

Outbound webhooks (HMAC-signed) and enterprise connectors (Confluence/Slack/Jira). Connectors run in
DRY_RUN by default (no real network) so the system is demoable offline; set live config to enable.
All calls are idempotent and retried with backoff by the caller.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field

from processiq_shared.models import SOP


def sign_payload(secret: str, payload: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def verify_signature(secret: str, payload: bytes, signature: str) -> bool:
    return hmac.compare_digest(sign_payload(secret, payload), signature)


@dataclass
class DispatchResult:
    target: str
    ok: bool
    detail: str
    dry_run: bool = True


@dataclass
class Connector:
    kind: str
    dry_run: bool = True
    config: dict = field(default_factory=dict)

    def publish_sop(self, sop: SOP) -> DispatchResult:
        title = sop.title
        if self.dry_run:
            return DispatchResult(self.kind, True, f"[dry-run] would publish '{title}' to {self.kind}")
        # Live path (owner: implement per connector API). Kept explicit + safe.
        return DispatchResult(self.kind, False, "live connector not configured", dry_run=False)


def build_webhook(secret: str, event: str, sop: SOP) -> tuple[bytes, str]:
    body = json.dumps({"event": event, "sopId": sop.id, "version": sop.version,
                       "tenantId": sop.tenant_id, "title": sop.title}).encode()
    return body, sign_payload(secret, body)
