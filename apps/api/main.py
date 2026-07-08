"""ProcessIQ control-plane API (design Sections 5, 10, 12).

Modular monolith mounting every bounded-context router + observability + a served demo UI.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # populate os.environ from .env so adapters (os.getenv) see HOSTED_VLM_* etc.

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from apps.api.metrics import MetricsMiddleware, metrics_response
from apps.api.routers import (
    admin,
    exports,
    integrations,
    jobs,
    notifications,
    processes,
    review,
    search,
    sops,
)
from apps.api.routers import health as health_router

app = FastAPI(
    title="ProcessIQ API",
    version="0.1.0",
    description="Enterprise AI Process Intelligence Platform — control plane.",
)

app.add_middleware(MetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten per §14.4 in prod
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id", uuid.uuid4().hex)
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):  # pragma: no cover
    return JSONResponse(
        status_code=500,
        content={"type": "about:blank", "title": "Internal Server Error", "status": 500,
                 "detail": str(exc), "instance": str(request.url)},
    )


for r in (health_router.router, processes.router, jobs.router, sops.router, review.router,
          search.router, exports.router, integrations.router, admin.router, notifications.router):
    app.include_router(r)


@app.get("/metrics", include_in_schema=False)
def metrics():
    return metrics_response()


# Serve the working demo UI (owner: Ayush). The production Next.js app lives in /frontend.
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/app", StaticFiles(directory=str(_static_dir), html=True), name="app")


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"name": "ProcessIQ API", "docs": "/docs", "app": "/app", "health": "/v1/health",
            "metrics": "/metrics"}
