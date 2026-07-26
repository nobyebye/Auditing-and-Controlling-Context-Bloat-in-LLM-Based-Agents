"""Provenance labeling and model-visible context segmentation."""

from __future__ import annotations

from context_auditor.domain.enums import PrivacyMode, SourceType
from context_auditor.domain.models import Message, TextSegment
from context_auditor.domain.text import hash_text, normalized_hash, store_text
from context_auditor.ports import Tokenizer

RETRIEVAL_MARKERS = ("retrieved context", "retrieval", "source passages", "context documents")
MEMORY_MARKERS = ("conversation history", "stored memory", "previous conversation", "chat history")
FRAMEWORK_MARKERS = ("agent scratchpad", "intermediate steps", "available tools", "format instructions")
TRACE_MARKERS = ("thought:", "action:", "observation:", "final answer:")


def label_source(message: Message) -> SourceType:
    explicit = message.metadata.get("source_type")
    if explicit:
        try:
            return SourceType(str(explicit))
        except ValueError:
            return SourceType.OTHER
    role = message.role.casefold()
    content = message.content.casefold()
    if role == "tool":
        return SourceType.TOOL
    if role in {"user", "human"}:
        return SourceType.USER
    if role in {"assistant", "ai"} and any(marker in content for marker in TRACE_MARKERS):
        return SourceType.GENERATED_TRACE
    if any(marker in content for marker in RETRIEVAL_MARKERS):
        return SourceType.RETRIEVAL
    if any(marker in content for marker in MEMORY_MARKERS):
        return SourceType.MEMORY
    if any(marker in content for marker in FRAMEWORK_MARKERS):
        return SourceType.FRAMEWORK
    if role == "system":
        return SourceType.SYSTEM
    if role in {"assistant", "ai"}:
        return SourceType.GENERATED_TRACE
    return SourceType.OTHER


def segment_messages(
    messages: tuple[Message, ...],
    tokenizer: Tokenizer,
    privacy_mode: PrivacyMode,
) -> tuple[TextSegment, ...]:
    segments: list[TextSegment] = []
    for message_index, message in enumerate(messages):
        source = label_source(message)
        message_id = f"m{message_index:04d}"
        parts = _split(message.content, source)
        for ordinal, raw_text in enumerate(parts):
            segments.append(
                TextSegment(
                    segment_id=f"{message_id}-s{ordinal:03d}",
                    parent_message_id=message_id,
                    message_index=message_index,
                    ordinal=ordinal,
                    role=message.role,
                    source_type=source.value,
                    text=store_text(raw_text, privacy_mode),
                    char_count=len(raw_text),
                    token_count=tokenizer.count(raw_text),
                    content_hash=hash_text(raw_text),
                    normalized_hash=normalized_hash(raw_text),
                    privacy_mode=privacy_mode.value,
                    source_id=(
                        str(message.metadata["source_id"])
                        if message.metadata.get("source_id") is not None
                        else None
                    ),
                    relevance_score=(
                        float(message.metadata["relevance_score"])
                        if message.metadata.get("relevance_score") is not None
                        else None
                    ),
                )
            )
    return tuple(segments)


def _split(content: str, source: SourceType) -> tuple[str, ...]:
    if source not in {SourceType.RETRIEVAL, SourceType.MEMORY}:
        return (content,)
    lines = tuple(line.strip() for line in content.splitlines() if line.strip())
    if len(lines) <= 1:
        return (content,)
    return lines[1:] if lines[0].endswith(":") else lines
