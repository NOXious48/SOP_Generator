"""Inference Gateway (design Sections 5.11, 12.4, 15.7).

Unified model access. All model calls go through `infer(task, payload)` where task is one of
`profiles.TASK_*`. The active hardware profile (MODEL_PROFILE env: mock | local-6gb | server-24gb |
cloud) decides which model serves the task, on which device, with what quantization — agents are
profile-agnostic and never change when the deployment moves 6 GB dev box -> 24 GB SSH server -> cloud.

Responsibilities implemented here:
- profile resolution (profiles.py)
- VRAM governor: residency budget + single-flight lease for heavy models sharing one GPU
- automatic Tier-2 fallback (spec.fallback, hosted API) when the primary backend fails
- perception/OCR result cache keyed by sha256(image) (cache.py) — hits skip the GPU entirely

Owner (Pushp): sbert embeddings adapter still TODO in adapters.py.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any

from .cache import InferenceCache, sha256_file
from .profiles import TASK_DETECTION, TASK_OCR, ModelSpec, Profile, load_profile

CACHEABLE_TASKS = frozenset({TASK_DETECTION, TASK_OCR})


class InferenceError(RuntimeError):
    pass


class VramGovernor:
    """Guards a single shared GPU.

    - Residency: a model may only load if the sum of resident models fits the profile budget.
      Profiles are sized so their models always fit; a violation means a misconfigured profile,
      so we fail loudly instead of OOMing the GPU mid-job.
    - Single-flight: heavy models (spec.single_flight) serialize inference calls so concurrent
      jobs queue instead of spiking VRAM. vLLM-backed models skip this (continuous batching).
    """

    def __init__(self, budget_mb: int) -> None:
        self._budget_mb = budget_mb
        self._resident: dict[str, int] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._mutex = threading.Lock()

    def _ensure_resident(self, spec: ModelSpec) -> None:
        with self._mutex:
            if spec.name in self._resident:
                return
            used = sum(self._resident.values())
            if used + spec.est_vram_mb > self._budget_mb:
                raise InferenceError(
                    f"VRAM budget exceeded loading '{spec.name}' "
                    f"({spec.est_vram_mb} MB needed, {self._budget_mb - used} MB free of "
                    f"{self._budget_mb} MB) — fix the profile, do not load models ad hoc")
            self._resident[spec.name] = spec.est_vram_mb
            self._locks[spec.name] = threading.Lock()

    @contextmanager
    def lease(self, spec: ModelSpec):
        if spec.device != "cuda" or spec.est_vram_mb <= 0:
            yield
            return
        self._ensure_resident(spec)
        if spec.single_flight:
            with self._locks[spec.name]:
                yield
        else:
            yield


class InferenceGateway:
    def __init__(self, profile: str | None = None) -> None:
        self.profile: Profile = load_profile(profile)
        self.governor = VramGovernor(self.profile.vram_budget_mb)
        self.cache = InferenceCache()

    def infer(self, task: str, payload: dict[str, Any]) -> dict[str, Any]:
        spec = self.profile.models.get(task)
        if spec is None:
            raise InferenceError(f"task '{task}' not defined in profile '{self.profile.name}'")
        cache_key = self._cache_key(task, spec, payload)
        if cache_key is not None and (hit := self.cache.get(cache_key)) is not None:
            hit["cached"] = True
            return hit
        try:
            with self.governor.lease(spec):
                out = self._dispatch(spec, task, payload)
        except Exception as primary_err:
            if spec.fallback is None:
                raise
            try:
                with self.governor.lease(spec.fallback):
                    out = self._dispatch(spec.fallback, task, payload)
            except Exception as fallback_err:
                raise InferenceError(
                    f"'{spec.name}' failed and fallback '{spec.fallback.name}' failed: "
                    f"{fallback_err}") from primary_err
            out["fallback_from"] = spec.name
            return out  # fallback results are not cached under the primary's key
        if cache_key is not None:
            self.cache.set(cache_key, out)
        return out

    @staticmethod
    def _cache_key(task: str, spec: ModelSpec, payload: dict[str, Any]) -> str | None:
        """Perception/OCR results are deterministic per (task, model, image) — cache them."""
        image_path = payload.get("image_path")
        if task not in CACHEABLE_TASKS or not image_path or spec.backend == "mock":
            return None
        try:
            digest = sha256_file(image_path)
        except OSError:
            return None  # unreadable file: let the backend produce the real error
        return f"infer:{task}:{spec.name}:{digest}"

    def _dispatch(self, spec: ModelSpec, task: str, payload: dict[str, Any]) -> dict[str, Any]:
        if spec.max_pixels is not None:
            payload.setdefault("max_pixels", spec.max_pixels)
        if spec.backend == "mock":
            return {"model": spec.name, "mode": "mock", "task": task, "echo": payload}
        from . import adapters  # lazy: heavy deps only when a real backend is selected
        if spec.backend == "hosted":
            text = adapters.hosted_chat(
                prompt=payload.get("prompt", ""), system=payload.get("system", ""),
                json_mode=payload.get("json_mode", False))
            return {"model": spec.name, "task": task, "text": text}
        if spec.backend == "vllm":
            text = adapters.vllm_chat(
                prompt=payload.get("prompt", ""), system=payload.get("system", ""),
                json_mode=payload.get("json_mode", False))
            return {"model": spec.name, "task": task, "text": text}
        if spec.backend == "ollama":
            text = adapters.ollama_chat(
                prompt=payload.get("prompt", ""), system=payload.get("system", ""),
                json_mode=payload.get("json_mode", False))
            return {"model": spec.name, "task": task, "text": text}
        if spec.backend == "paddle":
            regions = adapters.ocr_local(payload["image_path"])
            return {"model": spec.name, "task": task, "regions": regions}
        if spec.backend == "omniparser":
            elements = adapters.detect_elements(payload["image_path"], device=spec.device)
            return {"model": spec.name, "task": task, "elements": elements}
        raise InferenceError(
            f"backend '{spec.backend}' for '{spec.name}' not implemented yet "
            f"(owner: Divya — see adapters.py)")


gateway = InferenceGateway()
