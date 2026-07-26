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
        findings: list[BloatFinding] = []
        seen: dict[str, list[TextSegment]] = {}
        for segment in trace.segments:
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
                overlap = query_overlap_ratio(segment.text, query)
                if overlap < relevance_threshold:
                    findings.append(
                        BloatFinding(
                            segment.segment_id,
                            segment.source_type,
                            "low_query_relevance",
                            1.0 - overlap,
                        )
                    )
            prior.append(segment)
        return tuple(findings)
