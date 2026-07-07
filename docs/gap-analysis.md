# ProcessIQ — Target vs. Built (Gap Analysis)

> Snapshot: 2026-07-08. Target = `processiq-design/` Sections 00–22. Status verified on the
> `local-6gb` profile (RTX 3060 6GB dev box).

## 1. Vision vs. Reality

| Layer (design §4.2) | Target | Built so far | Status |
|---|---|---|---|
| Input | Images, PDF, video, Figma, diagrams | Real image upload, validation, preprocess, pHash dedup | 🟡 images only |
| Vision AI | OmniParser + PaddleOCR + layout + grounding | **Real:** OmniParser v2 (GPU), PaddleOCR (CPU), IoU text↔element association, geometric layout | 🟢 core done |
| Reasoning | VLM workflow inference, intent, process graph | Heuristic/mock (no VLM key yet); linear sequence fallback | 🔴 mock |
| Knowledge | Vector + graph KB, search, RAG chat | Naive in-memory search; no vector/graph DB wired | 🔴 stub |
| Output | SOP + 8 export formats, editor, review, publish | All 8 exports render; approve/publish gates; draft SOP | 🟢 done (content quality gated by Reasoning) |
| Cross-cutting | SSO, RBAC, audit, observability | Header-stub auth, RBAC roles, audit log, /metrics, agent traces | 🟡 scaffold |

## 2. Feature Checklist (from slides/poster)

| Feature | Status |
|---|---|
| Screenshot → structured SOP | 🟢 works end-to-end (SOP text mock-quality until VLM) |
| Element detection + bboxes + confidence | 🟢 real (268 elements on test image) |
| OCR + text-element association | 🟢 real (300 regions, 266 auto-labeled) |
| Visual-to-text traceability (step → screenshot region) | 🟢 in UI (click step → highlight bbox) |
| Confidence scores + review flags | 🟢 per-step + overall |
| Editable/reviewable SOP + publish gates | 🟡 approve/publish yes; rich editing no |
| Duplicate screen detection | 🟢 pHash on upload |
| Async jobs + live progress | 🟢 polling (SSE/WS designed, not built) |
| Agent execution traces (AI observability) | 🟢 API + UI panel |
| Multi-format export (md/html/json/bpmn/tests/rpa/docx/pdf) | 🟢 all render + download |
| Web interface | 🟡 working demo UI; production Next.js app not started |
| Workflow/transition inference across screens | 🔴 linear order only |
| AI suggestions (improve/rewrite/translate) | 🔴 not built |
| Knowledge base + semantic search + chat | 🔴 stub |
| Integrations (Jira/Confluence/Slack/…) | 🔴 stubs |
| PII redaction | 🔴 not built (design §5.2) |
| Feedback learning loop | 🔴 capture-only design, not wired |
| Video/PDF/Figma ingestion | 🔴 v2 scope |

## 3. Infrastructure & Model Serving

| Item | Target | Built | Status |
|---|---|---|---|
| Hardware profiles | 6GB dev → 24GB SSH → cloud | `MODEL_PROFILE` in gateway + docs §15.7 | 🟢 |
| VRAM governor + single-flight | §12.4 | Implemented + tested | 🟢 |
| sha256 perception cache | §NFR-082 | Redis w/ file fallback; verified ~3000× speedup | 🟢 |
| Tier-2 hosted fallback | HR-9 | Implemented; proven live | 🟢 |
| vLLM on 24GB server (M2.5) | §13.12 | Config ready, not yet migrated | 🔴 pending server |
| Postgres/Mongo/Redis/Qdrant/MinIO/NATS | §9 | docker-compose exists; app uses in-memory store + local objstore | 🔴 not wired |
| K8s/Helm/CI-CD/OTel/Grafana | §13 | Scaffolds/design only | 🔴 |

## 4. Industry Standards — Where We Stand

**Meets standard practice already**
- Typed contracts everywhere (Pydantic schemas = single source of truth)
- RFC 9457 error model; request-id middleware; append-only audit records
- Profile-driven model serving (env-swappable, agents hardware-agnostic)
- Graceful degradation: model → fallback tier → mock; crash-safe async jobs
- Deterministic caching keyed by content hash
- 39 automated tests incl. failure paths; clean module boundaries per design

**Below industry bar (known, by scaffold design — must close before real users)**
- **Persistence:** in-memory store — data lost on restart (needs Postgres/Mongo per §9)
- **AuthN:** trust-the-headers stub — needs OIDC/JWT (§14.1) before any network exposure
- **Tenant isolation:** logical only, no RLS enforcement
- **Async:** thread-per-job, no durable queue/retries/DLQ (§12.2–12.3)
- **Observability:** basic metrics + traces, no OTel pipeline/dashboards/alerts
- **Security:** no PII redaction, no rate limits, CORS `*`, no prompt-injection guards active
- **No CI/CD** running the test suite on push

## 5. Priority to Close the Gap (recommended order)

1. Hosted VLM key → real reasoning/generation (unlocks the actual product value)
2. Golden 5-screen flow → multi-screen SOP with real transitions
3. Postgres persistence (kills the restart-wipes-everything problem)
4. OIDC auth + CORS tightening (prerequisite for hosting on the SSH server)
5. M2.5: migrate to `server-24gb` profile (vLLM self-hosted)
6. Production frontend (Next.js) — the demo UI buys time but isn't the product
