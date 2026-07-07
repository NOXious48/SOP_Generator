"""Smoke-test OmniParser v2 detection through the inference gateway on a real screenshot.

Usage (from repo root, venv active):
    python -m scripts.omniparser_smoke <image_path> [--no-captions]

Runs gateway.infer("detection", ...) on the `local-6gb` profile, prints the detected elements,
and writes an annotated overlay next to the input image (<name>.overlay.png).
The second run on the same image should be a cache hit (cached=True, no GPU).
"""
from __future__ import annotations

import os
import sys
import time


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        raise SystemExit(2)
    image_path = args[0]
    if "--no-captions" in sys.argv:
        os.environ["OMNIPARSER_CAPTIONS"] = "0"
    os.environ.setdefault("MODEL_PROFILE", "local-6gb")

    from apps.inference_gateway.gateway import InferenceGateway

    gw = InferenceGateway()
    print(f"profile={gw.profile.name}  image={image_path}")

    t0 = time.perf_counter()
    out = gw.infer("detection", {"image_path": image_path})
    dt = time.perf_counter() - t0
    elements = out.get("elements", [])
    print(f"model={out.get('model')}  cached={out.get('cached', False)}  "
          f"elements={len(elements)}  latency={dt:.2f}s")
    for el in sorted(elements, key=lambda e: -e["confidence"])[:15]:
        x, y, w, h = el["bbox"]
        cap = (el.get("caption") or "")[:60]
        print(f"  conf={el['confidence']:.2f}  bbox=({x:.3f},{y:.3f},{w:.3f},{h:.3f})  {cap}")

    overlay_path = _draw_overlay(image_path, elements)
    print(f"overlay written: {overlay_path}")

    t0 = time.perf_counter()
    out2 = gw.infer("detection", {"image_path": image_path})
    print(f"second call: cached={out2.get('cached', False)}  "
          f"latency={time.perf_counter() - t0:.3f}s")


def _draw_overlay(image_path: str, elements: list[dict]) -> str:
    from PIL import Image, ImageDraw

    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    width, height = img.size
    for i, el in enumerate(elements):
        x, y, w, h = el["bbox"]
        box = (x * width, y * height, (x + w) * width, (y + h) * height)
        draw.rectangle(box, outline=(124, 58, 237), width=2)
        label = f"{i}:{el['confidence']:.2f}"
        draw.text((box[0] + 2, max(0, box[1] - 12)), label, fill=(37, 99, 235))
    out_path = os.path.splitext(image_path)[0] + ".overlay.png"
    img.save(out_path)
    return out_path


if __name__ == "__main__":
    main()
