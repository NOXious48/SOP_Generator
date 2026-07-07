# ProcessIQ — Pitch Outline (owner: Rajat)

**Tagline:** See it. Understand it. Document it. Improve it — all with Agentic AI.

**One-liner:** ProcessIQ turns any UI screenshot or screen sequence into an enterprise-grade,
confidence-scored SOP — an AI Process Intelligence Platform, not just an SOP generator.

## 3–5 min flow
1. **Problem (30s):** process docs are manual, expensive, and stale within one UI release.
2. **Reframe (20s):** the *visual* is the source of truth; the SOP is a generated, versioned
   projection — like compiling source to a binary.
3. **Live demo (120s):** open `/app` → create "Create New Order" process → run pipeline → watch the
   5-agent chain → generated SOP with per-step confidence + screenshot traceability → approve a
   flagged step → publish → export to PDF/BPMN. (Fallback: pre-recorded clip.)
4. **Architecture money-slide (40s):** 5 layers (Input→Vision→Reasoning→Knowledge→Output), 10-agent
   LangGraph pipeline, grounded + audited + confidence-gated.
5. **Why it wins (30s):** grounding (no hallucinated steps), human-in-the-loop, provenance, exports,
   enterprise security/RBAC/audit — maps to all 16 judging categories.
6. **Business impact (20s):** ≥80% analyst-hour reduction; always-accurate docs; faster onboarding.
7. **Roadmap + ask (20s):** video ingestion, process knowledge graph, RPA hand-off, drift monitoring.

## Judge Q&A crib
- *Accuracy?* Specialized CV perception + grounded generation + validation; human gate on low conf.
- *Hallucination?* Cite-or-omit: every step must reference a detected element; ungrounded → flagged.
- *Security?* RBAC + tenant isolation, PII redaction pre-persist/pre-model, prompt-injection defense.
- *Scale/cost?* Async queue + GPU autoscale + model tiering + caching; runs on a 6GB laptop via
  local OCR/detection + a small quantized LLM (Ollama) or a hosted API.
- *Moat?* The accumulating process knowledge graph + feedback-tuned models per tenant.
