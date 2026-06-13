"""Conservative context bloat mitigation utilities."""

from __future__ import annotations

from dataclasses import dataclass, field

from .metrics import compute_metrics
from .schema import AuditTrace, Segment
from .text_similarity import jaccard_similarity, query_overlap_ratio


@dataclass(frozen=True)
class MitigationReport:
    original_tokens: int
    mitigated_tokens: int
    removed_segments: int
    removed_tokens: int
    removed_by_source: dict[str, int] = field(default_factory=dict)

    @property
    def token_reduction_ratio(self) -> float:
        if self.original_tokens == 0:
            return 0.0
        return self.removed_tokens / self.original_tokens

    def to_dict(self) -> dict:
        return {
            "original_tokens": self.original_tokens,
            "mitigated_tokens": self.mitigated_tokens,
            "removed_segments": self.removed_segments,
            "removed_tokens": self.removed_tokens,
            "removed_by_source": self.removed_by_source,
            "token_reduction_ratio": self.token_reduction_ratio,
        }


def remove_exact_duplicate_segments(
    trace: AuditTrace,
    source_types: tuple[str, ...] = ("retrieval", "memory", "tool"),
) -> tuple[list[Segment], MitigationReport]:
    seen: set[tuple[str, str]] = set()
    kept: list[Segment] = []
    removed_by_source: dict[str, int] = {}
    removed_segments = 0
    removed_tokens = 0

    for segment in trace.segments:
        key = (segment.source_type, segment.normalized_hash)
        if segment.source_type in source_types and key in seen:
            removed_segments += 1
            removed_tokens += segment.token_count
            removed_by_source[segment.source_type] = removed_by_source.get(segment.source_type, 0) + segment.token_count
            continue
        seen.add(key)
        kept.append(segment)

    return kept, _build_report(trace, kept, removed_segments, removed_tokens, removed_by_source)


def remove_near_duplicate_segments(
    trace: AuditTrace,
    source_types: tuple[str, ...] = ("retrieval", "memory", "tool"),
    threshold: float = 0.85,
) -> tuple[list[Segment], MitigationReport]:
    kept: list[Segment] = []
    removed_by_source: dict[str, int] = {}
    removed_segments = 0
    removed_tokens = 0

    for segment in trace.segments:
        if segment.source_type in source_types and any(
            segment.source_type == previous.source_type
            and jaccard_similarity(segment.text, previous.text) >= threshold
            for previous in kept
        ):
            removed_segments += 1
            removed_tokens += segment.token_count
            removed_by_source[segment.source_type] = removed_by_source.get(segment.source_type, 0) + segment.token_count
            continue
        kept.append(segment)

    return kept, _build_report(trace, kept, removed_segments, removed_tokens, removed_by_source)


def filter_irrelevant_segments(
    trace: AuditTrace,
    query: str,
    source_types: tuple[str, ...] = ("retrieval", "memory"),
    min_overlap_ratio: float = 0.05,
) -> tuple[list[Segment], MitigationReport]:
    kept: list[Segment] = []
    removed_by_source: dict[str, int] = {}
    removed_segments = 0
    removed_tokens = 0

    for segment in trace.segments:
        if segment.source_type in source_types and query_overlap_ratio(segment.text, query) < min_overlap_ratio:
            removed_segments += 1
            removed_tokens += segment.token_count
            removed_by_source[segment.source_type] = removed_by_source.get(segment.source_type, 0) + segment.token_count
            continue
        kept.append(segment)

    return kept, _build_report(trace, kept, removed_segments, removed_tokens, removed_by_source)


def _build_report(
    trace: AuditTrace,
    kept: list[Segment],
    removed_segments: int,
    removed_tokens: int,
    removed_by_source: dict[str, int],
) -> MitigationReport:
    mitigated_metrics = compute_metrics(kept)
    original_tokens = int(trace.metrics.get("total_tokens", 0))
    return MitigationReport(
        original_tokens=original_tokens,
        mitigated_tokens=int(mitigated_metrics.get("total_tokens", 0)),
        removed_segments=removed_segments,
        removed_tokens=removed_tokens,
        removed_by_source=dict(sorted(removed_by_source.items())),
    )
