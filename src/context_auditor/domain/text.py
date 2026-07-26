"""Deterministic text normalization, hashing, and privacy policies."""

from __future__ import annotations

import hashlib
import re

from .enums import PrivacyMode

SPACE_RE = re.compile(r"\s+")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d ().-]{7,}\d)(?!\w)")
BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
SECRET_RE = re.compile(
    r"(?i)\b(api[_ -]?key|authorization|access[_ -]?token|secret)\b(\s*[:=]\s*)([^\s,;]+)"
)


def normalize_text(text: str) -> str:
    return SPACE_RE.sub(" ", text.strip().casefold())


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalized_hash(text: str) -> str:
    return hash_text(normalize_text(text))


def redact_text(text: str) -> str:
    redacted = BEARER_RE.sub("Bearer [REDACTED]", text)
    redacted = SECRET_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", redacted)
    redacted = EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)
    return PHONE_RE.sub("[REDACTED_PHONE]", redacted)


def store_text(text: str, mode: PrivacyMode) -> str:
    if mode is PrivacyMode.FULL:
        return text
    if mode is PrivacyMode.HASH_ONLY:
        return f"[HASH:{hash_text(text)}]"
    return redact_text(text)
