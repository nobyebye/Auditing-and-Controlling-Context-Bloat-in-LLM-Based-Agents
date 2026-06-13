"""Deterministic text similarity helpers for bloat analysis."""

from __future__ import annotations

import re

TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")


def token_set(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text)}


def jaccard_similarity(left: str, right: str) -> float:
    left_tokens = token_set(left)
    right_tokens = token_set(right)
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def query_overlap_ratio(text: str, query: str) -> float:
    query_tokens = token_set(query)
    if not query_tokens:
        return 0.0
    return len(token_set(text) & query_tokens) / len(query_tokens)
