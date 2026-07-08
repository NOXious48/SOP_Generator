# ProcessIQ — Enterprise AI Process Intelligence Platform

Visual Process Understanding & SOP Generation Engine. Converts UI screenshots / screen sequences /
diagrams into structured, editable, confidence-scored Standard Operating Procedures (SOPs) with
visual-to-text traceability (each step cites a screenshot region + the control to click).

> Design source of truth: `../processiq-design/` (Sections 00–22). This repo implements it.

## What works today

- **Real VLM SOP generation** — upload screenshots + a one-line description of the process, and a
  hosted vision-LLM (Google Gemini, free tier) produces a grounded step-by-step SOP in **one call**.
- **Local perception** — OmniParser v2 (GPU element detection) + PaddleOCR, behind a hardware-profile
  inference gateway (`local-6gb` / `server-24gb` / `cloud`) with a VRAM governor and sha256 cache.
- **Control plane** — FastAPI: processes, uploads (validate + preprocess + perceptual-hash dedup),
  async jobs with live progress, SOP versioning, review/approve/publish gates, 8 export formats.
- **Web UI** at `/app` — describe + drag-drop screenshots → run → SOP with confidence, click a step
  to highlight the button on the screenshot; agent trace panel.

## Canonical pipeline
```
Raw visuals -> 1 Visual Perception -> 2 OCR/Text Extraction -> 3 Workflow Understanding
            -> 4 SOP Generation -> 5 Validation & Confidence -> structured SOP

VLM path (hosted model configured): screenshots + user instruction -> 1 grounded SOP call
```

## Monorepo layout
```
processiq_shared/      Pydantic models: SOP schema, agent state, events, enums (the contracts)
apps/api               Control plane (FastAPI): processes, jobs, sops, review, search, exports,
                       integrations, admin, health; serves the demo UI at /app
apps/orchestrator      Ordered agent pipeline (run_pipeline) + VLM pipeline (run_vlm_pipeline)
apps/inference_gateway Unified model access: hardware profiles, VRAM governor, sha256 cache,
                       adapters (OmniParser, PaddleOCR, hosted/vLLM VLM)
agents/                vision, ocr, layout, gui, workflow, reasoning, kg, generation, validation,
                       confidence; sop_vlm (real VLM SOP generation)
services/              worker entrypoints (preprocess, export, integration)
frontend/              Next.js + TS app (production UI) [scaffold]
infra/                 Dockerfiles, docker-compose, k8s/helm [scaffold]
scripts/               demo + smoke utilities (omniparser_smoke, ocr_smoke)
docs/                  gap-analysis, backlog
```

## Quickstart (control plane, no GPU needed)
```powershell
# from repo root
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn apps.api.main:app --reload --port 8000
# open http://localhost:8000/app  ·  /docs  ·  /v1/health
```

## Enable real SOP generation (hosted VLM)
Copy `.env.example` to `.env` and set a free Google Gemini key (aistudio.google.com):
```
INFERENCE_MODE=hosted
HOSTED_VLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
HOSTED_VLM_API_KEY=<your-key>
HOSTED_MODEL=gemini-2.5-flash
```
`.env` is gitignored — never commit your key. With it set, the API auto-selects the VLM pipeline:
one multi-image call (instruction + screenshots) → grounded SOP.

## Local perception models (optional, GPU)
```powershell
# download OmniParser v2 weights into weights/omniparser, then:
$env:MODEL_PROFILE='local-6gb'; $env:OCR_DEVICE='cpu'
python -m scripts.omniparser_smoke <screenshot.png>   # GPU element detection
python -m scripts.ocr_smoke        <screenshot.png>   # PaddleOCR
```

## Full stack (Docker)
```powershell
docker compose up -d          # postgres, mongo, redis, qdrant, minio, nats
```

## Tests
```powershell
python -m pytest tests -q     # offline/mocked; never touches a real key (see tests/conftest.py)
```

## Status
Working vertical slice: describe + upload screenshots → real Gemini-generated, grounded SOP →
review → publish → export. Perception (OmniParser/PaddleOCR) verified on the `local-6gb` profile.
See `docs/gap-analysis.md` for target-vs-built and `../processiq-design/` for the full design.
