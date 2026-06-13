"""Content hashing and normalization."""

from __future__ import annotations

import hashlib
import re

SPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    return SPACE_RE.sub(" ", text.strip().lower())


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalized_hash(text: str) -> str:
    return hash_text(normalize_text(text))
