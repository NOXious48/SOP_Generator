"""Knowledge base search + chat (design Section 5.6, TDD-13). Owner: Divya/Pushp.

Scaffold uses keyword scoring over published SOPs with tenant scoping. Swap the scorer for hybrid
vector + BM25 + reranker; swap `chat` for RAG with the same citation contract.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.api.security_ctx import Principal, require
from apps.api.store import store

router = APIRouter(prefix="/v1", tags=["search"])


def _score(sop, terms: list[str]) -> int:
    hay = " ".join([sop.title, sop.objective] + [s.action + " " + s.description for s in sop.steps]).lower()
    return sum(hay.count(t) for t in terms)


@router.get("/search")
def search(q: str, limit: int = 20, p: Principal = Depends(require("search:read"))) -> dict:
    terms = [t for t in q.lower().split() if t]
    results = []
    for sop in store.sops.values():
        if sop.tenant_id != p.tenant_id:
            continue
        score = _score(sop, terms)
        if score > 0:
            results.append({"sopId": sop.id, "title": sop.title, "score": score,
                            "confidence": sop.overall_confidence, "state": sop.state.value})
    results.sort(key=lambda r: r["score"], reverse=True)
    return {"query": q, "results": results[:limit]}


class ChatBody(BaseModel):
    query: str


@router.post("/chat")
def chat(body: ChatBody, p: Principal = Depends(require("search:read"))) -> dict:
    hits = search(body.query, 3, p)["results"]
    if not hits:
        return {"answer": "No relevant SOPs found.", "citations": []}
    top = hits[0]
    return {
        "answer": f"Based on '{top['title']}' (confidence {top['confidence']}), "
                  f"see the referenced SOP for the step-by-step procedure.",
        "citations": [{"sopId": h["sopId"], "title": h["title"]} for h in hits],
    }
