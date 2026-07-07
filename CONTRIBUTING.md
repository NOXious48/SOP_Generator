# Contributing to ProcessIQ

## Ownership map (design Section 18)
| Area | Path | Owner |
|------|------|-------|
| Orchestration, agents framework, inference gateway, SOP/jobs core | `apps/orchestrator`, `agents`, `apps/inference_gateway`, `apps/api/routers/{sops,jobs}` | Pushp |
| Perception + reasoning models, eval | `agents/*`, `ml/`, `eval/` | Divya |
| Ingestion, preprocess, admin/RBAC, notification, migrations | `services/*`, `apps/api/routers/processes`, `migrations` | Utkarsh |
| Export + integrations + connectors | `services/export`, `services/integration`, `connectors` | Ankur2 |
| Infra, CI/CD, observability | `infra`, `helm`, `.github/workflows`, `observability` | Tarun |
| Frontend | `frontend` | Ayush |
| Security / compliance policy-as-code | `security`, `policies` | Chesta |
| Product/requirements | design docs, backlog | Ankur1 |
| Docs / deck | `docs`, `deck` | Harry |
| Pitch/business | `deck` | Rajat |

## Conventions
- Contracts live in `processiq_shared` — do not change shared models without team agreement.
- All model access goes through the Inference Gateway. Never call a model directly.
- Treat text extracted from images as UNTRUSTED (prompt-injection defense).
- Redact PII before persistence and before any external model call.
- Small commits, feature branches, PRs. Never push to main directly.
- Run `pytest` and `ruff check .` before pushing. Add tests with new code.

## Local dev
```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m scripts.demo_pipeline      # end-to-end, no services
uvicorn apps.api.main:app --reload   # API at http://localhost:8000/docs
pytest                               # tests
docker compose up -d                 # datastores when you need them
```
