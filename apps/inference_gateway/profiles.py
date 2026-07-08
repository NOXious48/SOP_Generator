"""Hardware profiles for the inference gateway (design Section 15.7).

A profile maps logical tasks (detection, ocr, vlm, embeddings) to a ModelSpec: which model, which
backend, which device, what quantization, and how much VRAM it needs. The active profile is selected
via the MODEL_PROFILE env var; agents never reference profiles — they call `gateway.infer(task, ...)`.

Profiles:
- mock         no models, deterministic outputs (tests / scaffold; default)
- local-6gb    dev workstation: local CV (OmniParser + PaddleOCR) + hosted VLM API
- server-24gb  SSH GPU server: self-hosted vLLM (Qwen2.5-VL-7B AWQ) + CV; hosted API = fallback
- cloud        GA scale: external vLLM/Triton pools reached over the network
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

TASK_DETECTION = "detection"
TASK_OCR = "ocr"
TASK_VLM = "vlm"  # screen semantics, workflow reasoning, SOP generation
TASK_EMBEDDINGS = "embeddings"


@dataclass(frozen=True)
class ModelSpec:
    name: str                      # registry id, e.g. "omniparser-v2"
    backend: str                   # mock | hosted | paddle | omniparser | vllm | ollama | sbert
    device: str = "cpu"            # cuda | cpu | api
    quantization: str | None = None
    est_vram_mb: int = 0           # resident VRAM once loaded (cuda only)
    max_pixels: int | None = None  # image-token cap (Qwen2.5-VL dynamic resolution can blow KV cache)
    single_flight: bool = False    # serialize inference calls (heavy model on a shared GPU)
    fallback: ModelSpec | None = None  # Tier-2 escalation (HR-9); hosted API in every GPU profile


@dataclass(frozen=True)
class Profile:
    name: str
    vram_budget_mb: int
    models: dict[str, ModelSpec] = field(default_factory=dict)


_HOSTED_VLM = ModelSpec(name="hosted-vlm", backend="hosted", device="api")

_MOCK = Profile(
    name="mock",
    vram_budget_mb=0,
    models={
        TASK_DETECTION: ModelSpec(name="mock-detection", backend="mock"),
        TASK_OCR: ModelSpec(name="mock-ocr", backend="mock"),
        TASK_VLM: ModelSpec(name="mock-vlm", backend="mock"),
        TASK_EMBEDDINGS: ModelSpec(name="mock-embeddings", backend="mock"),
    },
)

# Dev workstation: 6 GB cannot co-host a useful VLM with the CV models — local GPU does perception,
# the hosted API does reasoning/generation.
_LOCAL_6GB = Profile(
    name="local-6gb",
    vram_budget_mb=5500,  # leave headroom below 6144 for the desktop/display
    models={
        TASK_DETECTION: ModelSpec(
            name="omniparser-v2", backend="omniparser", device="cuda",
            est_vram_mb=2500, single_flight=True, fallback=_HOSTED_VLM),
        TASK_OCR: ModelSpec(
            name="paddleocr", backend="paddle",
            device=os.getenv("OCR_DEVICE", "cuda"),  # set OCR_DEVICE=cpu to free VRAM
            est_vram_mb=1500, single_flight=True, fallback=_HOSTED_VLM),
        TASK_VLM: _HOSTED_VLM,
        TASK_EMBEDDINGS: ModelSpec(name="bge-small-en-v1.5", backend="sbert", device="cpu"),
    },
)

# 24 GB SSH server: fully self-hosted; vLLM continuous-batches so no single-flight on the VLM.
_SERVER_24GB = Profile(
    name="server-24gb",
    vram_budget_mb=23000,
    models={
        TASK_VLM: ModelSpec(
            name="qwen2.5-vl-7b-instruct-awq", backend="vllm", device="cuda",
            quantization="awq", est_vram_mb=11000, max_pixels=1_003_520,
            fallback=_HOSTED_VLM),
        TASK_DETECTION: ModelSpec(
            name="omniparser-v2", backend="omniparser", device="cuda",
            est_vram_mb=2500, single_flight=True, fallback=_HOSTED_VLM),
        TASK_OCR: ModelSpec(
            name="paddleocr", backend="paddle", device="cuda",
            est_vram_mb=1500, single_flight=True, fallback=_HOSTED_VLM),
        TASK_EMBEDDINGS: ModelSpec(
            name="bge-large-en-v1.5", backend="sbert", device="cuda", est_vram_mb=1500),
    },
)

# GA scale: models served by external vLLM/Triton pools (Sections 12.4/13); no local VRAM to govern.
_CLOUD = Profile(
    name="cloud",
    vram_budget_mb=0,
    models={
        TASK_VLM: ModelSpec(name="qwen2.5-vl-7b-instruct", backend="vllm", device="api",
                            max_pixels=1_003_520, fallback=_HOSTED_VLM),
        TASK_DETECTION: ModelSpec(name="omniparser-v2", backend="omniparser", device="api",
                                  fallback=_HOSTED_VLM),
        TASK_OCR: ModelSpec(name="paddleocr", backend="paddle", device="api",
                            fallback=_HOSTED_VLM),
        TASK_EMBEDDINGS: ModelSpec(name="bge-large-en-v1.5", backend="sbert", device="api"),
    },
)

PROFILES: dict[str, Profile] = {p.name: p for p in (_MOCK, _LOCAL_6GB, _SERVER_24GB, _CLOUD)}


def load_profile(name: str | None = None) -> Profile:
    key = (name or os.getenv("MODEL_PROFILE", "mock")).strip().lower()
    if key not in PROFILES:
        raise ValueError(f"unknown MODEL_PROFILE '{key}'; expected one of {sorted(PROFILES)}")
    return PROFILES[key]
