"""ProcessIQ control-plane API (design Sections 5, 10, 12).

Modular monolith mounting every bounded-context router + observability + a served demo UI.
"""
from __future__ import annotations

import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from apps.api.metrics import MetricsMiddleware, metrics_response
from apps.api.routers import (
    admin,
    chat,
    exports,
    feedback,
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

def _start_ocr_warmup() -> None:
    """Preload the OCR model in a background thread at boot so no user waits for the first load.
    Disable with WARMUP_OCR=0. No-op unless the active profile uses PaddleOCR (skips mock/tests)."""
    import os

    if os.getenv("WARMUP_OCR", "1") == "0":
        return

    def _run() -> None:
        try:
            from apps.inference_gateway.adapters import warmup_ocr

            warmup_ocr()
        except Exception:  # noqa: BLE001 - warmup must never crash the server
            pass

    threading.Thread(target=_run, name="ocr-warmup", daemon=True).start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _start_ocr_warmup()  # boot stays instant; model loads in the background
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
          feedback.router, chat.router):
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
