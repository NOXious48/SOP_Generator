# ProcessIQ — System & Model Architecture

> **How to turn these into an image:** every diagram below is written in **Mermaid**. Paste any block
> into **https://mermaid.live** (Actions → *Export PNG / SVG*), or open this file in VS Code with the
> *Markdown Preview Mermaid* extension, or view it on GitHub (which renders Mermaid inline) and
> screenshot it. All diagrams include a color theme so the exported image looks presentation-ready.

---

## 1. High-level system architecture

Five layers, contract-first (typed Pydantic models) so every box is swappable.

```mermaid
flowchart TB
  %% ---------- styling ----------
  classDef ui       fill:#EEF2FF,stroke:#6366F1,stroke-width:2px,color:#1E1B4B;
  classDef api      fill:#ECFEFF,stroke:#06B6D4,stroke-width:2px,color:#083344;
  classDef pipe     fill:#F5F3FF,stroke:#7C3AED,stroke-width:2px,color:#2E1065;
  classDef gate     fill:#FFF7ED,stroke:#F97316,stroke-width:2px,color:#431407;
  classDef data     fill:#F0FDF4,stroke:#22C55E,stroke-width:2px,color:#052E16;
  classDef cross    fill:#FEF2F2,stroke:#EF4444,stroke-width:1.5px,color:#450A0A;

  subgraph UI["🖥️ WEB UI — /app · /admin · /user"]
    direction LR
    U1["Upload · reorder · lightbox"]
    U2["Live progress · perception overlays"]
    U3["SOP editor · versions · export"]
    U4["Drift check · chat"]
    U5["Improvement inbox / suggestions"]
  end
  class UI,U1,U2,U3,U4,U5 ui;

  subgraph CP["⚙️ CONTROL PLANE — FastAPI modular monolith"]
    direction LR
    C1["processes · jobs · sops"]
    C2["review · improvements · drift"]
    C3["chat · exports · search"]
    C4["integrations · notifications · feedback"]
    C5["admin · health · metrics"]
  end
  class CP,C1,C2,C3,C4,C5 api;

  subgraph AI["🧠 AI PIPELINE — agent state machine"]
    direction LR
    A1["VLM SOP generation"]
    A2["OCR box-grounding"]
    A3["Validation (grounding)"]
    A4["Confidence scoring"]
    A5["(CV perception: vision · OCR · layout)"]
  end
  class AI,A1,A2,A3,A4,A5 pipe;

  subgraph IG["🔌 INFERENCE GATEWAY — one API, many backends"]
    direction LR
    G1["Hardware profiles<br/>mock · local-6gb · server-24gb · cloud"]
    G2["Adapters: Gemini VLM · PaddleOCR · OmniParser"]
    G3["VRAM governor · response cache"]
  end
  class IG,G1,G2,G3 gate;

  subgraph DS["💾 STATE & STORAGE"]
    direction LR
    D1["Store: in-memory + JSON snapshot"]
    D2["Object store (screenshots)"]
    D3["Hash-chained audit log"]
  end
  class DS,D1,D2,D3 data;

  XC["🔐 Cross-cutting: RBAC · tenant isolation · PII redaction · prompt-injection defense · observability"]:::cross

  UI -- "REST + async jobs + SSE" --> CP
  CP -- "run job" --> AI
  AI -- "model calls" --> IG
  CP <-->|read / write| DS
  AI <-->|state| DS
  XC -.-> CP
  XC -.-> AI
```

---

## 2. The two generation pipelines

ProcessIQ ships a deterministic, ordered **agent state machine** with two configurations. The **VLM
fast path** (default, hosted Gemini) lets the multimodal model read the screenshots directly and skips
the heavy computer-vision perception stages; the **full CV path** runs local detection/OCR/layout
agents for on-prem GPU deployments. Both end in the same grounding + confidence gates.

```mermaid
flowchart LR
  classDef fast fill:#F5F3FF,stroke:#7C3AED,stroke-width:2px,color:#2E1065;
  classDef cv   fill:#ECFEFF,stroke:#0891B2,stroke-width:2px,color:#083344;
  classDef gate fill:#FFF7ED,stroke:#F97316,stroke-width:2px,color:#431407;

  IN(["📤 Screenshots + instruction"]):::gate

  subgraph FAST["VLM FAST PATH  (hosted Gemini — default)"]
    direction LR
    F1["Generation<br/>VlmSopGenerationAgent"]:::fast
  end

  subgraph FULL["FULL CV PATH  (local GPU — optional)"]
    direction LR
    P1["Vision"]:::cv --> P2["OCR"]:::cv --> P3["Layout"]:::cv --> P4["GUI understanding"]:::cv
    P4 --> P5["Workflow"]:::cv --> P6["Reasoning"]:::cv --> P7["Knowledge graph"]:::cv --> P8["Generation"]:::cv
  end

  subgraph GATE["SHARED ASSURANCE GATES"]
    direction LR
    V["Validation<br/>(grounding / hallucination guard)"]:::gate --> C["Confidence<br/>(threshold + aggregate)"]:::gate
  end

  OUT(["📝 Structured, grounded SOP"]):::gate

  IN --> F1 --> GATE
  IN --> P1
  P8 --> GATE
  GATE --> OUT
```

---

## 3. End-to-end request flow

From upload to a published SOP, with the async job + streamed progress.

```mermaid
sequenceDiagram
  autonumber
  actor Admin
  participant UI as Web UI
  participant API as Control Plane (FastAPI)
  participant JOB as Job Runner (async)
  participant AI as AI Pipeline
  participant GW as Inference Gateway
  participant DB as Store / Object store

  Admin->>UI: Upload screenshots + instruction
  UI->>API: POST /v1/processes/{id}/uploads:file
  API->>DB: preprocess → PNG, pHash, persist
  Admin->>UI: Run AI pipeline
  UI->>API: POST /v1/jobs (async)
  API->>JOB: enqueue job
  API-->>UI: 202 jobId
  loop live progress
    UI->>API: GET /v1/jobs/{id} · SSE /v1/stream
    API-->>UI: stage %, status
  end
  JOB->>AI: run_vlm_pipeline(state)
  AI->>GW: VLM call (all screenshots + instruction)
  GW-->>AI: structured SOP JSON
  AI->>GW: OCR grounding (snap boxes)
  AI->>AI: Validation + Confidence gates
  AI->>DB: save SOP v1 (+ immutable version)
  UI->>API: GET /v1/sops/{id}
  API-->>UI: SOP (steps, boxes, confidence, flags)
  Admin->>UI: edit / approve / publish → new version
```

---

## 4. The role-based improvement loop

Readers submit suggestions; authors curate them and regenerate an improved version — the old one is
kept in history. Server-side RBAC enforces the boundary (not just the UI).

```mermaid
flowchart TB
  classDef user  fill:#EEF2FF,stroke:#6366F1,stroke-width:2px,color:#1E1B4B;
  classDef admin fill:#F5F3FF,stroke:#7C3AED,stroke-width:2px,color:#2E1065;
  classDef sys   fill:#F0FDF4,stroke:#22C55E,stroke-width:2px,color:#052E16;

  subgraph USER["👤 USER  (/user · Viewer)"]
    direction TB
    Ua["Browse SOPs & versions (read-only)"]:::user
    Ub["💡 Suggest — per step or whole SOP"]:::user
    Uc["Track status: Open → Resolved"]:::user
  end

  subgraph ADMIN["🛠️ ADMIN  (/admin · Author)"]
    direction TB
    Aa["Improvement inbox"]:::admin
    Ab["Curate: edit wording · resolve · dismiss"]:::admin
    Ac["Generate improved version<br/>(folds suggestions into refine)"]:::admin
  end

  subgraph SYS["🧠 System"]
    direction TB
    Sa["Refine pipeline<br/>(new instruction)"]:::sys
    Sb["New immutable version"]:::sys
  end

  Ub -- "POST /suggestions" --> Aa
  Aa --> Ab --> Ac
  Ac -- "refine_sop_id + instruction" --> Sa --> Sb
  Sb -- "resolved_version" --> Uc
```

---

## 5. Confidence & assurance model

The **CONFIDENCE SCORE** is a multi-signal, evidence-anchored reliability index — not a black-box
number.

```mermaid
flowchart LR
  classDef sig  fill:#F5F3FF,stroke:#7C3AED,stroke-width:2px,color:#2E1065;
  classDef gate fill:#FFF7ED,stroke:#F97316,stroke-width:2px,color:#431407;
  classDef out  fill:#F0FDF4,stroke:#22C55E,stroke-width:2px,color:#052E16;

  S1["Per-step epistemic<br/>confidence cᵢ ∈ [0,1]"]:::sig
  S2["Grounding check<br/>evidence exists?"]:::gate
  S3["OCR corroboration<br/>label ↔ text similarity"]:::gate
  S4["Threshold gate<br/>cᵢ < τ=0.75 → flag"]:::gate
  AGG["Aggregate<br/>overall = (1/N) Σ cᵢ"]:::sig
  BAND["Assurance band<br/>High ≥80% · Moderate 60–79% · Low <60%"]:::out
  REV["NEEDS_REVIEW<br/>if any step flagged"]:::gate

  S1 --> AGG
  S2 -->|ungrounded → POSSIBLE_HALLUCINATION| REV
  S3 -->|fail-safe: keep VLM box| S1
  S4 -->|LOW_CONFIDENCE| REV
  S1 --> S4
  AGG --> BAND
```

---

## 6. Deployment & hardware profiles

The **same code** runs from a laptop to a GPU server; `MODEL_PROFILE` selects the backend.

```mermaid
flowchart TB
  classDef p fill:#ECFEFF,stroke:#06B6D4,stroke-width:2px,color:#083344;

  APP["ProcessIQ (FastAPI + UI, one container)"]:::p
  APP --> M1["mock<br/>fake models · tests / Docker demo"]:::p
  APP --> M2["local-6gb<br/>hosted Gemini + PaddleOCR (CPU)<br/>6 GB dev laptop"]:::p
  APP --> M3["server-24gb<br/>self-hosted Qwen2.5-VL (vLLM) + PaddleOCR (GPU)<br/>24 GB Linux server"]:::p
  APP --> M4["cloud<br/>external model pools · GA scale"]:::p
```

---

## 7. Component reference

| Layer | Component | Responsibility |
| --- | --- | --- |
| **Web UI** | `apps/api/static/` (HTML + Tailwind + vanilla JS) | upload, live progress, perception overlays, SOP editor, versions, drift, chat, improvement inbox / suggestions |
| **Control plane** | `apps/api/` (FastAPI) | 14 routers: processes · jobs · sops · review · improvements · drift · chat · exports · search · integrations · notifications · feedback · admin · health |
| **Security & governance** | `security_ctx.py`, `audit.py`, `processiq_shared/security.py` | RBAC per action, tenant scoping, PII redaction, prompt-injection defense, SHA-256 hash-chained audit |
| **Orchestrator** | `apps/orchestrator/graph.py` | ordered agent state machine (`run_pipeline` / `run_vlm_pipeline`) with progress callbacks |
| **AI agents** | `agents/` | `sop_vlm` (VLM generation + OCR grounding), `perception` (vision/OCR/layout/GUI), `reasoning` (workflow/knowledge-graph), `generation` (validation/confidence) |
| **Inference gateway** | `apps/inference_gateway/` | profiles, adapters (Gemini VLM, PaddleOCR, OmniParser), VRAM governor, response cache |
| **State & storage** | `store.py`, `objstore.py` | durable in-memory + atomic JSON snapshot (`data/store.json`); on-disk screenshot object store; immutable SOP versions |
| **Contracts** | `processiq_shared/` | Pydantic v2 models, agent state, enums, events — one typed source of truth across API + agents |
| **Exports** | `services/export.py` | PDF · HTML · DOCX · Markdown · JSON · XML · BPMN · test cases · RPA — with embedded, annotated screenshots |

---

## 8. Technology at a glance

```mermaid
mindmap
  root(("ProcessIQ"))
    Backend
      FastAPI · Python 3.12
      Pydantic v2 contracts
      Async jobs · SSE
    AI / ML
      Gemini 2.5 Flash VLM
      PaddleOCR PP-OCRv5
      OmniParser v2
      Qwen2.5-VL / vLLM server
    Vision and imaging
      Pillow PNG re-encode
      Perceptual hash drift + dedup
    Data
      JSON snapshot store
      Object store
      Prod: Postgres · Mongo · Redis · Qdrant · Neo4j · MinIO
    Delivery
      HTML + Tailwind UI
      Docker + compose
      Prometheus metrics
      pytest · ruff · CI
```

---

<div align="center">
<sub>ProcessIQ — See it. Understand it. Document it. Improve it. — all with agentic AI.</sub>
</div>
