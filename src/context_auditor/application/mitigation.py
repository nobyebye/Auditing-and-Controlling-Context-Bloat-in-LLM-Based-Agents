"""Source-aware message mitigation with auditable decisions."""

from __future__ import annotations

from dataclasses import dataclass

from context_auditor.analytics import jaccard_similarity, query_overlap_ratio
from context_auditor.application.segmentation import label_source
from context_auditor.domain.enums import SourceType
from context_auditor.domain.models import Message, MitigationDecision
from context_auditor.domain.text import normalized_hash
from context_auditor.ports import Tokenizer


@dataclass(frozen=True)
class MitigationResult:
    messages: tuple[Message, ...]
    decisions: tuple[MitigationDecision, ...]


class ApplyMitigation:
    MANAGED_SOURCES = {SourceType.RETRIEVAL, SourceType.MEMORY, SourceType.TOOL}

    def __init__(self, tokenizer: Tokenizer) -> None:
        self.tokenizer = tokenizer

    def execute(
        self,
        messages: tuple[Message, ...],
        query: str,
        strategy: str,
        relevance_threshold: float = 0.05,
        near_duplicate_threshold: float = 0.8,
    ) -> MitigationResult:
        if strategy == "none":
            return MitigationResult(messages, ())
        if strategy not in {"exact", "source-aware", "last-n"}:
            raise ValueError(f"Unsupported mitigation strategy: {strategy}")
        if strategy == "last-n":
            return self._last_n(messages, keep=8)

        kept: list[Message] = []
        decisions: list[MitigationDecision] = []
        seen: dict[SourceType, list[Message]] = {}
        for index, message in enumerate(messages):
            source = label_source(message)
            prior = seen.setdefault(source, [])
            reason: str | None = None
            if source in self.MANAGED_SOURCES:
                if any(normalized_hash(item.content) == normalized_hash(message.content) for item in prior):
                    reason = "exact_duplicate"
                elif strategy == "source-aware" and any(
                    jaccard_similarity(item.content, message.content) >= near_duplicate_threshold for item in prior
                ):
                    reason = "near_duplicate"
                elif (
                    strategy == "source-aware"
                    and source in {SourceType.RETRIEVAL, SourceType.MEMORY}
                    and query_overlap_ratio(message.content, query) < relevance_threshold
                ):
                    reason = "low_query_relevance"
            if reason:
                decisions.append(self._decision(index, message, source, reason))
                continue
            kept.append(message)
            prior.append(message)
        return MitigationResult(tuple(kept), tuple(decisions))

    def _last_n(self, messages: tuple[Message, ...], keep: int) -> MitigationResult:
        if len(messages) <= keep:
            return MitigationResult(messages, ())
        protected = [item for item in messages if label_source(item) in {SourceType.SYSTEM, SourceType.USER}]
        tail = list(messages[-keep:])
        kept_list: list[Message] = []
        kept_ids: set[int] = set()
        for item in [*protected, *tail]:
            if id(item) not in kept_ids:
                kept_list.append(item)
                kept_ids.add(id(item))
        kept = tuple(kept_list)
        decisions = tuple(
            self._decision(index, message, label_source(message), "last_n_budget")
            for index, message in enumerate(messages)
            if id(message) not in kept_ids
        )
        return MitigationResult(kept, decisions)

    def _decision(
        self,
        index: int,
        message: Message,
        source: SourceType,
        reason: str,
    ) -> MitigationDecision:
        return MitigationDecision(
            segment_id=f"m{index:04d}",
            action="remove",
            reason=reason,
            source_type=source.value,
            removed_tokens=self.tokenizer.count(message.content),
        )
