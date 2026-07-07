"""Smoke-test PaddleOCR through the inference gateway on a real screenshot.

Usage (from repo root, venv active):
    python -m scripts.ocr_smoke <image_path>

Runs gateway.infer("ocr", ...) on the active profile (default local-6gb), prints the extracted
text regions, and writes an annotated overlay next to the input (<name>.ocr-overlay.png).
The second run on the same image should be a cache hit (cached=True, no model call).
"""
from __future__ import annotations

import os
import sys
import time


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    image_path = sys.argv[1]
    os.environ.setdefault("MODEL_PROFILE", "local-6gb")

    from apps.inference_gateway.gateway import InferenceGateway

    gw = InferenceGateway()
    ocr_spec = gw.profile.models["ocr"]
    print(f"profile={gw.profile.name}  ocr_device={ocr_spec.device}  image={image_path}")

    t0 = time.perf_counter()
    out = gw.infer("ocr", {"image_path": image_path})
    dt = time.perf_counter() - t0
    regions = out.get("regions", [])
    print(f"model={out.get('model')}  cached={out.get('cached', False)}  "
          f"regions={len(regions)}  latency={dt:.2f}s")
    for r in sorted(regions, key=lambda r: -r["confidence"])[:20]:
        x, y, w, h = r["bbox"]
        print(f"  conf={r['confidence']:.2f}  bbox=({x:.3f},{y:.3f},{w:.3f},{h:.3f})  {r['text'][:60]}")

    overlay_path = _draw_overlay(image_path, regions)
    print(f"overlay written: {overlay_path}")

    t0 = time.perf_counter()
    out2 = gw.infer("ocr", {"image_path": image_path})
    print(f"second call: cached={out2.get('cached', False)}  "
          f"latency={time.perf_counter() - t0:.3f}s")


def _draw_overlay(image_path: str, regions: list[dict]) -> str:
    from PIL import Image, ImageDraw

    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    width, height = img.size
    for r in regions:
        x, y, w, h = r["bbox"]
        box = (x * width, y * height, (x + w) * width, (y + h) * height)
        draw.rectangle(box, outline=(34, 197, 94), width=2)
    out_path = os.path.splitext(image_path)[0] + ".ocr-overlay.png"
    img.save(out_path)
    return out_path


if __name__ == "__main__":
    main()
