"""Model adapters for the inference gateway (design Sections 5.11, 12.4, 15.7).

Owners: Divya (models) + Pushp (gateway). Backends behind one interface:
- mock:       deterministic, offline (default; tests + demo)
- hosted:     hosted LLM/VLM API (OpenAI-compatible) — the VLM path on `local-6gb`, Tier-2 fallback everywhere
- vllm:       self-hosted vLLM OpenAI-compatible endpoint (Qwen2.5-VL AWQ) — the VLM path on `server-24gb`
- ollama:     local quantized LLM — offline experiments only, never the pipeline path (Section 15.7)
- paddle:     PaddleOCR on the local GPU/CPU
- omniparser: OmniParser v2 (YOLO interactable detector + Florence-2 captioner) on the local GPU

All adapters are lazy: heavy libraries are imported only when the backend is selected, so the core
app runs without them installed. Which backend serves which task is decided by the active hardware
profile (profiles.py), not by callers.
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx


# ---------- OCR ----------
def ocr_local(image_path: str) -> list[dict[str, Any]]:  # pragma: no cover - needs paddle
    """PaddleOCR (3.x API) text extraction.

    Returns regions matching the shared `TextRegion` contract: normalized bbox [x, y, w, h] in
    [0, 1] + confidence. Device via OCR_DEVICE (cpu on the Windows dev box; gpu on the Linux server).
    """
    from PIL import Image

    engine = _get_paddle()
    width, height = Image.open(image_path).size
    regions: list[dict[str, Any]] = []
    for page in engine.predict(image_path):
        data = page if "rec_texts" in page else page.get("res", {})  # dict-like OCRResult
        for text, score, poly in zip(data["rec_texts"], data["rec_scores"], data["rec_polys"]):
            xs = [float(p[0]) for p in poly]
            ys = [float(p[1]) for p in poly]
            x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
            regions.append({
                "text": text,
                "confidence": float(score),
                "bbox": [x0 / width, y0 / height, (x1 - x0) / width, (y1 - y0) / height],
            })
    return regions


_PADDLE = None


def _get_paddle():  # pragma: no cover
    global _PADDLE
    if _PADDLE is None:
        from paddleocr import PaddleOCR

        device = "gpu" if os.getenv("OCR_DEVICE", "cuda") == "cuda" else "cpu"
        _PADDLE = PaddleOCR(
            lang=os.getenv("OCR_LANG", "en"),
            device=device,
            use_doc_orientation_classify=False,  # screenshots are upright; skip extra models
            use_doc_unwarping=False,
            use_textline_orientation=False,
            # paddle 3.7 PIR executor + oneDNN crashes on Windows CPU
            # (ConvertPirAttribute2RuntimeAttribute); opt back in via OCR_MKLDNN=1 on Linux
            enable_mkldnn=os.getenv("OCR_MKLDNN", "0") == "1",
        )
    return _PADDLE


# ---------- Detection (OmniParser v2) ----------
_YOLO = None
_FLORENCE: tuple[Any, Any] | None = None


def detect_elements(image_path: str, device: str = "cuda") -> list[dict[str, Any]]:  # pragma: no cover - needs GPU + weights
    """OmniParser v2: YOLO interactable-element detection + Florence-2 element captions.

    Weights (download `microsoft/OmniParser-v2.0` from HuggingFace into OMNIPARSER_WEIGHTS):
      {OMNIPARSER_WEIGHTS}/icon_detect/model.pt
      {OMNIPARSER_WEIGHTS}/icon_caption/           (Florence-2 finetune; processor comes from
                                                    microsoft/Florence-2-base — the finetune repo
                                                    ships no processor files)

    Returns elements matching the shared `Element` contract: normalized bbox [x, y, w, h] in [0, 1].
    Set OMNIPARSER_CAPTIONS=0 to skip captioning (saves ~1 GB VRAM + latency on the 6 GB box).
    """
    from PIL import Image

    img = Image.open(image_path).convert("RGB")
    width, height = img.size
    yolo = _get_yolo()
    result = yolo.predict(
        img,
        conf=float(os.getenv("OMNIPARSER_BOX_THRESHOLD", "0.05")),
        iou=0.7,
        device=device,
        verbose=False,
    )[0]
    elements: list[dict[str, Any]] = []
    for (x1, y1, x2, y2), score in zip(result.boxes.xyxy.tolist(), result.boxes.conf.tolist()):
        elements.append({
            "type": "interactable",
            "bbox": [x1 / width, y1 / height, (x2 - x1) / width, (y2 - y1) / height],
            "confidence": float(score),
            "caption": None,
        })
    if elements and os.getenv("OMNIPARSER_CAPTIONS", "1") != "0":
        _caption_elements(img, elements, device)
    return elements


def _weights_dir() -> str:
    return os.getenv("OMNIPARSER_WEIGHTS", "weights/omniparser")


def _get_yolo():  # pragma: no cover
    global _YOLO
    if _YOLO is None:
        from ultralytics import YOLO

        _YOLO = YOLO(os.path.join(_weights_dir(), "icon_detect", "model.pt"))
    return _YOLO


def _get_florence(device: str):  # pragma: no cover
    global _FLORENCE
    if _FLORENCE is None:
        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor

        path = os.path.join(_weights_dir(), "icon_caption")
        dtype = torch.float16 if device == "cuda" else torch.float32
        processor = AutoProcessor.from_pretrained(
            os.getenv("FLORENCE_PROCESSOR", "microsoft/Florence-2-base"), trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            path, torch_dtype=dtype, trust_remote_code=True).to(device).eval()
        _FLORENCE = (model, processor)
    return _FLORENCE


def _caption_elements(img, elements: list[dict[str, Any]], device: str,
                      batch_size: int = 32) -> None:  # pragma: no cover
    """Fill captions using the OmniParser-finetuned Florence-2 ('<CAPTION>' prompt), batched."""
    import torch

    model, processor = _get_florence(device)
    width, height = img.size
    crops = []
    for el in elements:
        x, y, w, h = el["bbox"]
        crops.append(img.crop((int(x * width), int(y * height),
                               int((x + w) * width), int((y + h) * height))))
    dtype = torch.float16 if device == "cuda" else torch.float32
    for i in range(0, len(crops), batch_size):
        batch = crops[i:i + batch_size]
        inputs = processor(images=batch, text=["<CAPTION>"] * len(batch),
                           return_tensors="pt").to(device, dtype)
        with torch.inference_mode():
            ids = model.generate(
                input_ids=inputs["input_ids"], pixel_values=inputs["pixel_values"],
                max_new_tokens=20, num_beams=1, do_sample=False)
        for el, text in zip(elements[i:i + batch_size],
                            processor.batch_decode(ids, skip_special_tokens=True)):
            el["caption"] = text.strip()


# ---------- LLM / VLM (reasoning / generation) ----------
def llm_generate(prompt: str, system: str = "", json_mode: bool = False) -> str:
    """Route to the VLM backend for the active hardware profile.

    Resolution order: explicit INFERENCE_MODE env (mock|hosted|local|vllm) wins; otherwise the
    MODEL_PROFILE's `vlm` ModelSpec decides (local-6gb -> hosted, server-24gb -> vllm).
    """
    mode = os.getenv("INFERENCE_MODE") or _profile_vlm_mode()
    if mode == "local":
        return ollama_chat(prompt, system, json_mode)
    if mode == "vllm":
        return vllm_chat(prompt, system, json_mode)
    if mode == "hosted":
        return hosted_chat(prompt, system, json_mode)
    # mock: echo a minimal deterministic response
    return json.dumps({"note": "mock-llm", "prompt_chars": len(prompt)})


def _profile_vlm_mode() -> str:
    from .profiles import TASK_VLM, load_profile

    backend = load_profile().models[TASK_VLM].backend
    return {"hosted": "hosted", "vllm": "vllm", "ollama": "local"}.get(backend, "mock")


def ollama_chat(prompt: str, system: str = "", json_mode: bool = False) -> str:  # pragma: no cover
    base = os.getenv("OLLAMA_URL", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        **({"format": "json"} if json_mode else {}),
    }
    r = httpx.post(f"{base}/api/generate", json=payload, timeout=120)
    r.raise_for_status()
    return r.json().get("response", "")


def hosted_chat(prompt: str, system: str = "", json_mode: bool = False) -> str:  # pragma: no cover
    base = os.getenv("HOSTED_VLM_BASE_URL")
    key = os.getenv("HOSTED_VLM_API_KEY")
    model = os.getenv("HOSTED_MODEL", "gpt-4o-mini")
    if not base or not key:
        raise RuntimeError("HOSTED_VLM_BASE_URL / HOSTED_VLM_API_KEY not set")
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        **({"response_format": {"type": "json_object"}} if json_mode else {}),
    }
    r = httpx.post(f"{base}/chat/completions", json=body,
                   headers={"Authorization": f"Bearer {key}"}, timeout=120)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def vllm_chat(prompt: str, system: str = "", json_mode: bool = False) -> str:  # pragma: no cover
    """Self-hosted vLLM (OpenAI-compatible server) — `server-24gb` profile VLM path."""
    base = os.getenv("VLLM_BASE_URL", "http://localhost:8001/v1")
    model = os.getenv("VLLM_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct-AWQ")
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        **({"response_format": {"type": "json_object"}} if json_mode else {}),
    }
    headers = {}
    if key := os.getenv("VLLM_API_KEY"):
        headers["Authorization"] = f"Bearer {key}"
    r = httpx.post(f"{base}/chat/completions", json=body, headers=headers, timeout=180)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]
