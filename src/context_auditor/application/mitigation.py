"""Source-aware message mitigation with auditable decisions."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace

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
        verbose_tool_token_threshold: int = 80,
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
            replacement: Message | None = None
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
                elif (
                    strategy == "source-aware"
                    and source == SourceType.TOOL
                    and self.tokenizer.count(message.content) >= verbose_tool_token_threshold
                ):
                    compressed = compress_tool_output(message.content)
                    replacement = replace(
                        message,
                        content=compressed,
                        metadata={
                            key: value
                            for key, value in message.metadata.items()
                            if key != "bloat_labels"
                        },
                    )
                    decisions.append(
                        self._decision(
                            index,
                            message,
                            source,
                            "verbose_tool_output",
                            action="compress",
                            removed_tokens=max(
                                0,
                                self.tokenizer.count(message.content)
                                - self.tokenizer.count(compressed),
                            ),
                        )
                    )
            if reason:
                decisions.append(self._decision(index, message, source, reason))
                continue
            selected = replacement or message
            if source in self.MANAGED_SOURCES and any(
                normalized_hash(item.content) == normalized_hash(selected.content)
                for item in prior
            ):
                decisions.append(
                    self._decision(
                        index,
                        message,
                        source,
                        "exact_duplicate_after_transform",
                    )
                )
                continue
            kept.append(selected)
            prior.append(selected)
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
        action: str = "remove",
        removed_tokens: int | None = None,
    ) -> MitigationDecision:
        return MitigationDecision(
            segment_id=f"m{index:04d}",
            action=action,
            reason=reason,
            source_type=source.value,
            removed_tokens=(
                self.tokenizer.count(message.content)
                if removed_tokens is None
                else removed_tokens
            ),
        )


def compress_tool_output(text: str) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return f"{first_line}\n[verbose tool details removed]"
