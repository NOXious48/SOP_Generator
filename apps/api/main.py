"""ProcessIQ control-plane API (design Sections 5, 10, 12).

Modular monolith mounting every bounded-context router + observability + a served demo UI.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from apps.api.metrics import MetricsMiddleware, metrics_response
from apps.api.routers import (
    admin,
    chat,
    drift,
    exports,
    feedback,
    improvements,
    integrations,
    jobs,
    notifications,
    processes,
    review,
    search,
    sops,
)
from apps.api.routers import health as health_router

# Populate os.environ from .env so adapters (os.getenv) see HOSTED_VLM_* etc. Runs at import,
# before any request; agents read the env at call time.
load_dotenv()

def _preload_ocr() -> None:
    """Eagerly load PaddleOCR at startup (blocking) so it is ready the moment the app starts —
    no lazy first-request load. Set WARMUP_OCR=0 to skip (e.g. mock/demo without PaddleOCR
    installed). Guarded so a missing/misconfigured OCR stack never crashes boot."""
    import os

    if os.getenv("WARMUP_OCR", "1") == "0":
        return
    try:
        from apps.inference_gateway.adapters import _get_paddle

        _get_paddle()  # build the engine now, on the main startup path
    except Exception as exc:  # noqa: BLE001 - never crash boot if paddle is missing/misconfigured
        import logging

        logging.getLogger("processiq").warning("OCR preload skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _preload_ocr()  # PaddleOCR loads eagerly at startup (blocks boot until ready)
    yield


app = FastAPI(
    title="ProcessIQ API",
    version="0.1.0",
    description="Enterprise AI Process Intelligence Platform — control plane.",
    lifespan=lifespan,
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
          search.router, exports.router, integrations.router, admin.router, notifications.router,
          feedback.router, chat.router, drift.router, improvements.router):
    app.include_router(r)


@app.get("/metrics", include_in_schema=False)
def metrics():
    return metrics_response()


# Serve the working demo UI (owner: Ayush). The production Next.js app lives in /frontend.
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/app", StaticFiles(directory=str(_static_dir), html=True), name="app")


# Role-scoped entry points: the same UI, pre-set to the author (admin) or reader (user) experience.
@app.get("/admin", include_in_schema=False)
def admin_app() -> RedirectResponse:
    return RedirectResponse(url="/app/?role=admin")


@app.get("/user", include_in_schema=False)
def user_app() -> RedirectResponse:
    return RedirectResponse(url="/app/?role=user")


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"name": "ProcessIQ API", "docs": "/docs", "app": "/app",
            "admin": "/admin", "user": "/user", "health": "/v1/health", "metrics": "/metrics"}
