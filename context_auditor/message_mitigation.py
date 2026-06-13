"""Pre-call mitigation for model-visible messages."""

from __future__ import annotations

from .hashing import normalized_hash
from .provenance import SourceType, label_message_source
from .schema import Message
from .text_similarity import query_overlap_ratio


def apply_message_mitigation(
    messages: list[Message],
    strategy: str,
    query: str,
    min_overlap_ratio: float = 0.05,
) -> list[Message]:
    if strategy == "none":
        return list(messages)
    if strategy == "exact_duplicate_removal":
        return remove_duplicate_messages(messages)
    if strategy == "irrelevant_context_filter":
        return filter_irrelevant_context_lines(messages, query, min_overlap_ratio)
    if strategy == "combined":
        return filter_irrelevant_context_lines(remove_duplicate_messages(messages), query, min_overlap_ratio)
    raise ValueError(f"Unsupported mitigation strategy: {strategy}")


def remove_duplicate_messages(
    messages: list[Message],
    source_types: tuple[SourceType, ...] = (SourceType.RETRIEVAL, SourceType.MEMORY, SourceType.TOOL),
) -> list[Message]:
    seen: set[tuple[str, str]] = set()
    kept: list[Message] = []
    for message in messages:
        source_type = label_message_source(message)
        key = (source_type.value, normalized_hash(message.content))
        if source_type in source_types and key in seen:
            continue
        seen.add(key)
        kept.append(message)
    return kept


def filter_irrelevant_context_lines(
    messages: list[Message],
    query: str,
    min_overlap_ratio: float,
) -> list[Message]:
    kept: list[Message] = []
    for message in messages:
        source_type = label_message_source(message)
        if source_type not in {SourceType.RETRIEVAL, SourceType.MEMORY}:
            kept.append(message)
            continue

        lines = [line for line in message.content.splitlines() if line.strip()]
        if len(lines) <= 1:
            if query_overlap_ratio(message.content, query) >= min_overlap_ratio:
                kept.append(message)
            continue

        header = lines[0]
        body = [line for line in lines[1:] if query_overlap_ratio(line, query) >= min_overlap_ratio]
        if body:
            kept.append(
                Message(
                    role=message.role,
                    content="\n".join([header, *body]),
                    name=message.name,
                    metadata={**message.metadata, "mitigated": True},
                )
            )
    return kept
