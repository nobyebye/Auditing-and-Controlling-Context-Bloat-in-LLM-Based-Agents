"""Localize exact, near-duplicate, and irrelevant bloat to source segments."""

from __future__ import annotations

from context_auditor.analytics import jaccard_similarity, query_overlap_ratio
from context_auditor.domain.models import AuditTrace, BloatFinding, TextSegment


class LocalizeBloat:
    def execute(
        self,
        trace: AuditTrace,
        query: str,
        near_duplicate_threshold: float = 0.8,
        relevance_threshold: float = 0.05,
    ) -> tuple[BloatFinding, ...]:
        return localize_segments(
            trace.segments,
            query,
            near_duplicate_threshold=near_duplicate_threshold,
            relevance_threshold=relevance_threshold,
        )


def localize_segments(
    segments: tuple[TextSegment, ...],
    query: str,
    near_duplicate_threshold: float = 0.8,
    relevance_threshold: float = 0.05,
    verbose_tool_token_threshold: int = 80,
) -> tuple[BloatFinding, ...]:
    findings: list[BloatFinding] = []
    seen: dict[str, list[TextSegment]] = {}
    for segment in segments:
        prior = seen.setdefault(segment.source_type, [])
        exact = next(
            (
                item
                for item in prior
                if item.normalized_hash == segment.normalized_hash
            ),
            None,
        )
        if exact:
            findings.append(
                BloatFinding(
                    segment.segment_id,
                    segment.source_type,
                    "exact_duplicate",
                    1.0,
                    exact.segment_id,
                )
            )
        else:
            similarities = [
                (jaccard_similarity(segment.text, item.text), item) for item in prior
            ]
            closest = max(similarities, default=(0.0, None), key=lambda item: item[0])
            if closest[0] >= near_duplicate_threshold and closest[1] is not None:
                findings.append(
                    BloatFinding(
                        segment.segment_id,
                        segment.source_type,
                        "near_duplicate",
                        closest[0],
                        closest[1].segment_id,
                    )
                )
        if segment.source_type in {"retrieval", "memory"}:
            relevance = (
                segment.relevance_score
                if segment.relevance_score is not None
                else query_overlap_ratio(segment.text, query)
            )
            if relevance <= relevance_threshold:
                findings.append(
                    BloatFinding(
                        segment.segment_id,
                        segment.source_type,
                        "low_query_relevance",
                        1.0 - relevance,
                    )
                )
        if (
            segment.source_type == "tool"
            and segment.token_count >= verbose_tool_token_threshold
        ):
            findings.append(
                BloatFinding(
                    segment.segment_id,
                    segment.source_type,
                    "verbose_tool_output",
                    segment.token_count / verbose_tool_token_threshold,
                )
            )
        prior.append(segment)
    return tuple(findings)


def findings_by_segment(
    findings: tuple[BloatFinding, ...],
) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for finding in findings:
        labels = grouped.setdefault(finding.segment_id, [])
        if finding.label not in labels:
            labels.append(finding.label)
    return {segment_id: tuple(labels) for segment_id, labels in grouped.items()}
