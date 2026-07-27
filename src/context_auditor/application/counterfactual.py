"""Build auditable one-segment counterfactual request variants."""

from __future__ import annotations

from dataclasses import replace

from context_auditor.domain.models import (
    AuditTrace,
    CounterfactualVariant,
    Message,
    ModelRequestEnvelope,
)
from context_auditor.domain.text import hash_text

PROTECTED_SOURCES = frozenset(
    {"system", "user", "framework", "tool_schema"}
)


def build_counterfactual_variant(
    trace: AuditTrace,
    segment_ids: tuple[str, ...],
    *,
    variant_type: str,
) -> CounterfactualVariant:
    if not trace.request_envelope:
        raise ValueError("Counterfactual replay requires a captured request envelope")
    selected = [
        segment for segment in trace.segments if segment.segment_id in set(segment_ids)
    ]
    if len(selected) != len(set(segment_ids)):
        raise ValueError("One or more counterfactual segment IDs are missing")
    protected = [
        segment.segment_id
        for segment in selected
        if segment.source_type in PROTECTED_SOURCES
    ]
    if protected:
        raise ValueError(
            "Counterfactual variants cannot remove protected segments: "
            + ", ".join(protected)
        )
    by_message: dict[int, list[str]] = {}
    for segment in selected:
        by_message.setdefault(segment.message_index, []).append(segment.text)
    messages: list[Message] = []
    for index, message in enumerate(trace.request_envelope.messages):
        texts = by_message.get(index)
        if not texts:
            messages.append(message)
            continue
        content = message.content
        for text in texts:
            content = remove_segment_text(content, text)
        if content.strip():
            messages.append(replace(message, content=content.strip()))
    request = replace(trace.request_envelope, messages=tuple(messages))
    identity = (
        f"{trace.trace_id}:{variant_type}:{','.join(sorted(segment_ids))}"
    )
    return CounterfactualVariant(
        variant_id="cf-" + hash_text(identity)[:16],
        parent_trace_id=trace.trace_id,
        removed_segment_ids=tuple(sorted(segment_ids)),
        request=request,
        variant_type=variant_type,
    )


def remove_segment_text(content: str, segment_text: str) -> str:
    if content.strip() == segment_text.strip():
        return ""
    lines = content.splitlines()
    target = segment_text.strip()
    retained = [line for line in lines if line.strip() != target]
    if len(retained) != len(lines):
        return "\n".join(retained)
    if segment_text not in content:
        raise ValueError("Segment text is not present in its parent message")
    return content.replace(segment_text, "", 1)
