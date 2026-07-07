from __future__ import annotations

import os

from fastapi import APIRouter

from apps.api.config import settings
from processiq_shared import __version__

router = APIRouter(prefix="/v1", tags=["health"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "env": settings.app_env,
        "inference_mode": settings.inference_mode,
        "model_profile": os.getenv("MODEL_PROFILE", "mock"),
    }
