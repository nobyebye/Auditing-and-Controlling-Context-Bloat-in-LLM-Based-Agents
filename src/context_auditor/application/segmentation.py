"""Provenance labeling and model-visible context segmentation."""

from __future__ import annotations

import json

from context_auditor.domain.enums import PrivacyMode, SourceType
from context_auditor.domain.models import (
    Message,
    ModelRequestEnvelope,
    TextSegment,
)
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
        parts = _split(
            message.content,
            source,
            atomic=message.metadata.get("source_id") is not None,
        )
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
                    container_type="message",
                    container_index=message_index,
                )
            )
    return tuple(segments)


def segment_envelope(
    envelope: ModelRequestEnvelope,
    tokenizer: Tokenizer,
    privacy_mode: PrivacyMode,
) -> tuple[TextSegment, ...]:
    segments = list(segment_messages(envelope.messages, tokenizer, privacy_mode))
    for index, instruction in enumerate(envelope.system_instructions):
        segments.append(
            _envelope_segment(
                segment_id=f"i{index:04d}-s000",
                parent_id=f"i{index:04d}",
                message_index=len(envelope.messages) + index,
                role="system_instruction",
                source=SourceType.SYSTEM,
                text=instruction,
                tokenizer=tokenizer,
                privacy_mode=privacy_mode,
                container_type="system_instruction",
                container_index=index,
            )
        )
    for index, tool in enumerate(envelope.tools):
        raw = json.dumps(
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        segments.append(
            _envelope_segment(
                segment_id=f"t{index:04d}-s000",
                parent_id=f"t{index:04d}",
                message_index=(
                    len(envelope.messages)
                    + len(envelope.system_instructions)
                    + index
                ),
                role="tool_definition",
                source=SourceType.TOOL_SCHEMA,
                text=raw,
                tokenizer=tokenizer,
                privacy_mode=privacy_mode,
                container_type="tool_definition",
                container_index=index,
                source_id=tool.name,
            )
        )
    if envelope.response_format:
        raw = json.dumps(
            envelope.response_format,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        segments.append(
            _envelope_segment(
                segment_id="r0000-s000",
                parent_id="r0000",
                message_index=(
                    len(envelope.messages)
                    + len(envelope.system_instructions)
                    + len(envelope.tools)
                ),
                role="response_format",
                source=SourceType.FRAMEWORK,
                text=raw,
                tokenizer=tokenizer,
                privacy_mode=privacy_mode,
                container_type="response_format",
                container_index=0,
            )
        )
    return tuple(segments)


def _envelope_segment(
    *,
    segment_id: str,
    parent_id: str,
    message_index: int,
    role: str,
    source: SourceType,
    text: str,
    tokenizer: Tokenizer,
    privacy_mode: PrivacyMode,
    container_type: str,
    container_index: int,
    source_id: str | None = None,
) -> TextSegment:
    return TextSegment(
        segment_id=segment_id,
        parent_message_id=parent_id,
        message_index=message_index,
        ordinal=0,
        role=role,
        source_type=source.value,
        text=store_text(text, privacy_mode),
        char_count=len(text),
        token_count=tokenizer.count(text),
        content_hash=hash_text(text),
        normalized_hash=normalized_hash(text),
        privacy_mode=privacy_mode.value,
        source_id=source_id,
        container_type=container_type,
        container_index=container_index,
    )


def _split(
    content: str,
    source: SourceType,
    *,
    atomic: bool = False,
) -> tuple[str, ...]:
    if atomic or source not in {SourceType.RETRIEVAL, SourceType.MEMORY}:
        return (content,)
    lines = tuple(line.strip() for line in content.splitlines() if line.strip())
    if len(lines) <= 1:
        return (content,)
    return lines[1:] if lines[0].endswith(":") else lines
