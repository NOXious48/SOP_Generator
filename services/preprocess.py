"""Preprocessing service (design Section 5.2, TDD-02). Owners: Utkarsh + Divya.

Real work on CPU using Pillow:
- decode + validate image, normalize (RGB), auto-orient via EXIF, resize to a max dimension
- compute an average-hash (perceptual hash) for near-duplicate detection
- produce processed bytes for downstream perception
PII redaction runs on any extracted text elsewhere (OCR stage) via processiq_shared.security.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps


@dataclass
class Processed:
    width: int
    height: int
    phash: str
    data: bytes
    mode: str


def _average_hash(img: Image.Image, size: int = 8) -> str:
    small = img.convert("L").resize((size, size), Image.LANCZOS)
    pixels = list(small.getdata())
    avg = sum(pixels) / len(pixels)
    bits = "".join("1" if p >= avg else "0" for p in pixels)
    return f"{int(bits, 2):0{size * size // 4}x}"


def hamming(h1: str, h2: str) -> int:
    if len(h1) != len(h2):
        return max(len(h1), len(h2)) * 4
    x = int(h1, 16) ^ int(h2, 16)
    return bin(x).count("1")


def preprocess_image(raw: bytes, max_dim: int = 1600) -> Processed:
    img = Image.open(io.BytesIO(raw))
    img = ImageOps.exif_transpose(img)  # auto-orient
    img = img.convert("RGB")
    w, h = img.size
    scale = min(1.0, max_dim / max(w, h))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    phash = _average_hash(img)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Processed(width=img.width, height=img.height, phash=phash, data=buf.getvalue(), mode="RGB")


def is_duplicate(phash: str, existing: list[str], threshold: int = 5) -> bool:
    return any(hamming(phash, e) <= threshold for e in existing)
