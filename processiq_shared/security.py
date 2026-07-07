"""Security utilities shared across planes (owner: Chesta; design Sections 14.3, 14.5).

- PII detection + redaction (applied before persistence and before any model call).
- Untrusted-text sanitization (prompt-injection defense): any text extracted from images is data,
  never instructions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
TOKEN_RE = re.compile(r"(?i)(bearer\s+[a-z0-9._\-]+|api[_-]?key\s*[:=]\s*\S+)")
CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[ -]?)?(?:\(?\d{3}\)?[ -]?)?\d{3}[ -]?\d{4}\b")

# Prompt-injection markers we neutralize when treating extracted text as data.
INJECTION_PATTERNS = [
    re.compile(r"(?i)ignore\s+(?:all\s+|any\s+|the\s+|previous\s+|prior\s+)*instructions"),
    re.compile(r"(?i)disregard (the|all|your) (above|previous|system)"),
    re.compile(r"(?i)you are now"),
    re.compile(r"(?i)system prompt"),
    re.compile(r"(?i)act as (an?|the) (?:admin|root|developer)"),
]


def _luhn_ok(digits: str) -> bool:
    nums = [int(d) for d in digits if d.isdigit()]
    if len(nums) < 13:
        return False
    checksum = 0
    parity = len(nums) % 2
    for i, n in enumerate(nums):
        if i % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        checksum += n
    return checksum % 10 == 0


@dataclass
class RedactionResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def redact_pii(text: str) -> RedactionResult:
    """Mask/drop PII per policy. Returns redacted text + per-class counts."""
    counts: dict[str, int] = {}

    def _sub(pattern: re.Pattern, label: str, mask: str, s: str) -> str:
        found = pattern.findall(s)
        if found:
            counts[label] = counts.get(label, 0) + len(found)
        return pattern.sub(mask, s)

    out = text
    out = _sub(EMAIL_RE, "email", "[REDACTED_EMAIL]", out)
    out = _sub(TOKEN_RE, "auth_token", "[REDACTED_TOKEN]", out)

    def _card(m: re.Match) -> str:
        raw = m.group(0)
        if _luhn_ok(raw):
            counts["credit_card"] = counts.get("credit_card", 0) + 1
            return "[REDACTED_CARD]"
        return raw

    out = CARD_RE.sub(_card, out)
    out = _sub(PHONE_RE, "phone", "[REDACTED_PHONE]", out)
    return RedactionResult(text=out, counts=counts)


def sanitize_untrusted(text: str) -> str:
    """Neutralize instruction-like content in text extracted from images.

    The text is wrapped/annotated so downstream prompts treat it strictly as data.
    """
    cleaned = text
    for pat in INJECTION_PATTERNS:
        cleaned = pat.sub("[neutralized-instruction]", cleaned)
    return cleaned


def contains_injection(text: str) -> bool:
    return any(p.search(text) for p in INJECTION_PATTERNS)
