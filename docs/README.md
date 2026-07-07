# ProcessIQ Docs (owner: Harry)

## What's implemented (integrated, runnable today)
| Area | Owner | Where | Status |
|------|-------|-------|--------|
| Contracts (SOP schema, agent state, events, security) | Pushp/Chesta | `processiq_shared/` | done |
| Ingestion + upload + preprocess + dedup | Utkarsh | `apps/api/routers/processes.py`, `services/preprocess.py` | done |
| PII redaction + prompt-injection defense | Chesta | `processiq_shared/security.py` | done |
| RBAC + tenants + policies + audit | Utkarsh/Chesta | `security_ctx.py`, `routers/admin.py`, `audit.py` | done |
| 10-agent pipeline + orchestrator | Pushp | `agents/`, `apps/orchestrator/` | done (mock inference) |
| Inference gateway (mock/hosted/local GPU) | Pushp/Divya | `apps/inference_gateway/` | done |
| SOP service + versioning + publish gate | Pushp | `routers/sops.py` | done |
| Review/approval + sign-off | Utkarsh | `routers/review.py` | done |
| Search + chat (RAG-shaped) | Divya | `routers/search.py` | done (keyword) |
| Exports (md/html/json/xml/bpmn/testcases/rpa/docx/pdf) | Ankur2 | `services/export.py`, `routers/exports.py` | done |
| Integrations + webhooks (HMAC) | Ankur2 | `services/integration.py`, `routers/integrations.py` | done (dry-run) |
| Progress streaming (SSE) + event bus | Utkarsh/Pushp | `routers/notifications.py`, `apps/bus.py` | done |
| Metrics/observability | Tarun | `apps/api/metrics.py`, `/metrics` | done |
| CI + Helm + Docker + compose | Tarun | `.github/`, `helm/`, `infra/` | done |
| Eval harness + gate | Divya | `eval/harness.py` | done |
| Demo web UI | Ayush | `apps/api/static/` served at `/app` | done |
| License register | Chesta | `security/licenses.md` | done |
| Backlog + traceability | Ankur1 | `docs/backlog.csv` | done |
| Pitch | Rajat | `deck/pitch-outline.md` | done |

## Run
```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn apps.api.main:app --reload   # http://localhost:8000/app  and  /docs
python -m scripts.demo_pipeline
pytest
python -m eval.harness
```

## Enable the GPU (6GB) path
1. Install Ollama, pull a small model: `ollama pull qwen2.5:3b`
2. (optional) install AI deps for OCR/detection on GPU: see `requirements-ai.txt`
3. Set env: `INFERENCE_MODE=local`, `OLLAMA_MODEL=qwen2.5:3b`
4. Restart the API. Reasoning/generation now use the local LLM; OCR/detection use the GPU.
Hosted alternative: `INFERENCE_MODE=hosted` + `HOSTED_VLM_BASE_URL` + `HOSTED_VLM_API_KEY`.
