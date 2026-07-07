# ProcessIQ — Enterprise AI Process Intelligence Platform

Visual Process Understanding & SOP Generation Engine. Converts UI screenshots / screen sequences /
diagrams into structured, editable, confidence-scored Standard Operating Procedures (SOPs) with
visual-to-text traceability.

> Design source of truth: `../processiq-design/` (Sections 00–22). This repo implements it.

## Canonical pipeline
```
Raw visuals -> 1 Visual Perception -> 2 OCR/Text Extraction -> 3 Workflow Understanding
            -> 4 SOP Generation -> 5 Validation & Confidence -> structured SOP
```

## Monorepo layout
```
packages/shared        Pydantic models: SOP schema, agent state, events, enums (the contracts)
apps/api               Control plane (FastAPI modular monolith): processes, jobs, sops, review,
                       search, exports, integrations, admin, health
apps/orchestrator      LangGraph-style pipeline that runs the agents per job
apps/inference_gateway Unified model access (mock adapter now; vLLM/hosted VLM later)
agents/                vision, ocr, layout, gui, workflow, reasoning, kg, generation, validation,
                       confidence (stubbed, contract-complete)
services/              worker entrypoints (preprocess, export, integration) [scaffold]
frontend/              Next.js + TS app (ProcessIQ UI) [scaffold]
infra/                 Dockerfiles, docker-compose, k8s/helm [scaffold]
migrations/            SQL/Alembic migrations
security/policies/     policy-as-code (redaction, retention)
eval/                  model evaluation harness [scaffold]
scripts/               seed + dev utilities
docs/                  generated/rendered docs [scaffold]
```

## Quickstart (API, no GPU needed)
```powershell
# from repo root
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn apps.api.main:app --reload --port 8000
# open http://localhost:8000/docs  and  http://localhost:8000/v1/health
```

Run the end-to-end pipeline demo (fully mocked, no external services):
```powershell
python -m scripts.demo_pipeline
```

## Full stack (Docker)
```powershell
docker compose up -d          # postgres, mongo, redis, qdrant, minio, nats
```

## Status
Foundation scaffold: contracts + runnable control-plane API + mocked agent pipeline + a working
"Create New Order" demo. Team members flesh out their modules per `../processiq-design/dist/<name>`.

See `CONTRIBUTING.md` for conventions and the per-member ownership map.
