"""Trace-level auditing metrics."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .schema import Segment
from .text_similarity import jaccard_similarity


def compute_metrics(
    segments: list[Segment],
    cost_per_1k_tokens: float = 0.0,
    near_duplicate_threshold: float = 0.85,
) -> dict[str, Any]:
    total_tokens = sum(segment.token_count for segment in segments)
    total_chars = sum(segment.char_count for segment in segments)
    tokens_by_source: dict[str, int] = defaultdict(int)
    chars_by_source: dict[str, int] = defaultdict(int)
    hashes = Counter(segment.normalized_hash for segment in segments if segment.normalized_hash)
    duplicate_tokens_by_hash: dict[str, int] = defaultdict(int)
    first_seen_tokens: dict[str, int] = {}

    for segment in segments:
        tokens_by_source[segment.source_type] += segment.token_count
        chars_by_source[segment.source_type] += segment.char_count
        if segment.normalized_hash in first_seen_tokens:
            duplicate_tokens_by_hash[segment.normalized_hash] += segment.token_count
        else:
            first_seen_tokens[segment.normalized_hash] = segment.token_count

    source_ratios = {
        source: (tokens / total_tokens if total_tokens else 0.0)
        for source, tokens in sorted(tokens_by_source.items())
    }
    duplicate_segment_count = sum(count - 1 for count in hashes.values() if count > 1)
    redundant_tokens = sum(duplicate_tokens_by_hash.values())
    near_duplicate_segment_count, near_duplicate_tokens = compute_near_duplicate_counts(
        segments,
        threshold=near_duplicate_threshold,
    )
    redundancy_ratio = redundant_tokens / total_tokens if total_tokens else 0.0
    near_redundancy_ratio = near_duplicate_tokens / total_tokens if total_tokens else 0.0
    unique_information_ratio = 1.0 - redundancy_ratio if total_tokens else 0.0

    return {
        "total_tokens": total_tokens,
        "total_chars": total_chars,
        "tokens_by_source": dict(sorted(tokens_by_source.items())),
        "chars_by_source": dict(sorted(chars_by_source.items())),
        "source_ratios": source_ratios,
        "source_contribution_ratio": source_ratios,
        "duplicate_segment_count": duplicate_segment_count,
        "near_duplicate_segment_count": near_duplicate_segment_count,
        "redundant_tokens": redundant_tokens,
        "near_redundant_tokens": near_duplicate_tokens,
        "redundancy_ratio": redundancy_ratio,
        "near_redundancy_ratio": near_redundancy_ratio,
        "unique_information_ratio": unique_information_ratio,
        "estimated_cost": (total_tokens / 1000.0) * cost_per_1k_tokens,
    }


def compute_near_duplicate_counts(segments: list[Segment], threshold: float) -> tuple[int, int]:
    near_duplicate_count = 0
    near_duplicate_tokens = 0
    seen_by_source: dict[str, list[Segment]] = defaultdict(list)
    for segment in segments:
        source_segments = seen_by_source[segment.source_type]
        if any(jaccard_similarity(segment.text, previous.text) >= threshold for previous in source_segments):
            near_duplicate_count += 1
            near_duplicate_tokens += segment.token_count
        source_segments.append(segment)
    return near_duplicate_count, near_duplicate_tokens
