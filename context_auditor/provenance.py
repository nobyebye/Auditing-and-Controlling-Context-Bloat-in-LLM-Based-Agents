"""Rule-based provenance labeling for model-visible context."""

from __future__ import annotations

from enum import StrEnum

from .hashing import hash_text, normalized_hash
from .schema import Message, Segment
from .tokenization import count_tokens


class SourceType(StrEnum):
    SYSTEM = "system"
    USER = "user"
    FRAMEWORK = "framework"
    RETRIEVAL = "retrieval"
    MEMORY = "memory"
    TOOL = "tool"
    GENERATED_TRACE = "generated_trace"
    OTHER = "other"


RETRIEVAL_MARKERS = (
    "retrieved context",
    "retrieval",
    "retrieved document",
    "retrieved documents",
    "source passages",
    "context documents",
)

MEMORY_MARKERS = (
    "conversation history",
    "memory",
    "stored memory",
    "previous conversation",
    "chat history",
)

FRAMEWORK_MARKERS = (
    "agent scratchpad",
    "intermediate steps",
    "available tools",
    "tool names",
    "format instructions",
)

GENERATED_TRACE_MARKERS = (
    "thought:",
    "action:",
    "observation:",
    "final answer:",
)


def label_message_source(message: Message) -> SourceType:
    role = message.role.lower()
    content = message.content.lower()
    explicit_source = message.metadata.get("source_type")
    if explicit_source:
        return SourceType(explicit_source)

    if role == "tool":
        return SourceType.TOOL
    if role == "user" or role == "human":
        return SourceType.USER
    if role == "assistant" and any(marker in content for marker in GENERATED_TRACE_MARKERS):
        return SourceType.GENERATED_TRACE
    if any(marker in content for marker in RETRIEVAL_MARKERS):
        return SourceType.RETRIEVAL
    if any(marker in content for marker in MEMORY_MARKERS):
        return SourceType.MEMORY
    if any(marker in content for marker in FRAMEWORK_MARKERS):
        return SourceType.FRAMEWORK
    if role == "system":
        return SourceType.SYSTEM
    if role == "assistant":
        return SourceType.GENERATED_TRACE
    return SourceType.OTHER


def segment_messages(messages: list[Message]) -> list[Segment]:
    segments: list[Segment] = []
    for message_index, message in enumerate(messages):
        source_type = label_message_source(message)
        texts = split_message_into_segments(message.content, source_type)
        for part_index, text in enumerate(texts):
            segments.append(
                Segment(
                    segment_id=f"s{message_index:03d}_{part_index:02d}",
                    message_index=message_index,
                    role=message.role,
                    source_type=source_type.value,
                    text=text,
                    char_count=len(text),
                    token_count=count_tokens(text),
                    content_hash=hash_text(text),
                    normalized_hash=normalized_hash(text),
                )
            )
    return segments


def split_message_into_segments(content: str, source_type: SourceType) -> list[str]:
    if source_type not in {SourceType.RETRIEVAL, SourceType.MEMORY}:
        return [content]

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if len(lines) <= 1:
        return [content]

    body_lines = lines[1:] if lines[0].endswith(":") else lines
    return body_lines or [content]
