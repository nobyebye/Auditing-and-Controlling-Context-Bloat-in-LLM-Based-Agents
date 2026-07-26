"""Deterministic context-bloat metrics."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Iterable

from context_auditor.domain.models import TextSegment

TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def token_set(text: str) -> set[str]:
    return {token.casefold() for token in TOKEN_RE.findall(text)}


def jaccard_similarity(left: str, right: str) -> float:
    left_tokens, right_tokens = token_set(left), token_set(right)
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def query_overlap_ratio(text: str, query: str) -> float:
    query_tokens = token_set(query)
    return len(token_set(text) & query_tokens) / len(query_tokens) if query_tokens else 0.0


def compute_metrics(segments: Iterable[TextSegment], near_duplicate_threshold: float = 0.8) -> dict[str, Any]:
    items = list(segments)
    total_tokens = sum(item.token_count for item in items)
    total_chars = sum(item.char_count for item in items)
    tokens_by_source: dict[str, int] = defaultdict(int)
    hashes = Counter(item.normalized_hash for item in items)
    first_seen: set[str] = set()
    redundant_tokens = 0
    near_redundant_tokens = 0
    near_duplicate_count = 0
    seen_by_source: dict[str, list[TextSegment]] = defaultdict(list)

    for item in items:
        tokens_by_source[item.source_type] += item.token_count
        if item.normalized_hash in first_seen:
            redundant_tokens += item.token_count
        first_seen.add(item.normalized_hash)
        if any(
            jaccard_similarity(item.text, previous.text) >= near_duplicate_threshold
            for previous in seen_by_source[item.source_type]
        ):
            near_duplicate_count += 1
            near_redundant_tokens += item.token_count
        seen_by_source[item.source_type].append(item)

    duplicate_count = sum(count - 1 for count in hashes.values() if count > 1)
    source_ratios = {
        source: tokens / total_tokens if total_tokens else 0.0
        for source, tokens in sorted(tokens_by_source.items())
    }
    return {
        "total_tokens": total_tokens,
        "total_chars": total_chars,
        "tokens_by_source": dict(sorted(tokens_by_source.items())),
        "source_ratios": source_ratios,
        "duplicate_segment_count": duplicate_count,
        "near_duplicate_segment_count": near_duplicate_count,
        "redundant_tokens": redundant_tokens,
        "near_redundant_tokens": near_redundant_tokens,
        "redundancy_ratio": redundant_tokens / total_tokens if total_tokens else 0.0,
        "near_redundancy_ratio": near_redundant_tokens / total_tokens if total_tokens else 0.0,
        "unique_information_ratio": 1.0 - (redundant_tokens / total_tokens) if total_tokens else 0.0,
    }
