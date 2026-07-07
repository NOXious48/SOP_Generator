"""Inference gateway hardware profiles (design Section 15.7)."""
import pytest

from apps.inference_gateway.gateway import InferenceError, InferenceGateway, VramGovernor
from apps.inference_gateway.profiles import PROFILES, TASK_VLM, ModelSpec, load_profile

ALL_TASKS = {"detection", "ocr", "vlm", "embeddings"}


def test_default_profile_is_mock_and_echoes():
    g = InferenceGateway()
    out = g.infer(TASK_VLM, {"prompt": "hi"})
    assert out["mode"] == "mock"
    assert out["task"] == "vlm"


@pytest.mark.parametrize("name", sorted(PROFILES))
def test_every_profile_defines_all_tasks(name):
    assert set(load_profile(name).models) == ALL_TASKS


@pytest.mark.parametrize("name", sorted(PROFILES))
def test_profile_models_fit_vram_budget(name):
    p = load_profile(name)
    resident = sum(s.est_vram_mb for s in p.models.values() if s.device == "cuda")
    assert resident <= p.vram_budget_mb


def test_gpu_profiles_have_hosted_fallback_for_heavy_tasks():
    for name in ("local-6gb", "server-24gb"):
        p = load_profile(name)
        for task in ("detection", "ocr", "vlm"):
            spec = p.models[task]
            if spec.backend != "hosted":
                assert spec.fallback is not None and spec.fallback.backend == "hosted", (name, task)


def test_governor_rejects_over_budget_load():
    gov = VramGovernor(1000)
    big = ModelSpec(name="too-big", backend="vllm", device="cuda", est_vram_mb=2000)
    with pytest.raises(InferenceError, match="VRAM budget exceeded"):
        with gov.lease(big):
            pass


def test_governor_passes_through_cpu_and_api_specs():
    gov = VramGovernor(0)
    for device in ("cpu", "api"):
        with gov.lease(ModelSpec(name=f"m-{device}", backend="mock", device=device)):
            pass


def test_unknown_profile_and_task_fail_loudly():
    with pytest.raises(ValueError, match="unknown MODEL_PROFILE"):
        load_profile("nope")
    with pytest.raises(InferenceError, match="not defined in profile"):
        InferenceGateway().infer("nonexistent", {})


def test_fallback_chain_surfaces_both_failures(monkeypatch):
    # local-6gb detection: omniparser adapter not implemented -> hosted fallback without env -> error
    monkeypatch.delenv("HOSTED_VLM_BASE_URL", raising=False)
    monkeypatch.delenv("HOSTED_VLM_API_KEY", raising=False)
    g = InferenceGateway("local-6gb")
    with pytest.raises(InferenceError, match="fallback"):
        g.infer("detection", {"image_path": "x.png"})
