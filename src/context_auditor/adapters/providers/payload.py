"""Canonical provider payload construction and privacy-safe request records."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from context_auditor.domain.enums import PrivacyMode
from context_auditor.domain.models import (
    ModelRequestEnvelope,
    ProviderRequestRecord,
)
from context_auditor.domain.text import store_text


def build_openai_payload(
    envelope: ModelRequestEnvelope,
    model: str,
) -> dict[str, Any]:
    messages = [
        {"role": normalize_role(item.role), "content": item.content}
        for item in envelope.messages
    ]
    if envelope.system_instructions:
        messages = [
            {"role": "system", "content": instruction}
            for instruction in envelope.system_instructions
        ] + messages
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": envelope.generation_parameters.temperature,
        "max_tokens": envelope.generation_parameters.max_output_tokens,
    }
    if envelope.tools:
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": dict(tool.parameters),
                },
            }
            for tool in envelope.tools
        ]
    if envelope.response_format:
        payload["response_format"] = dict(envelope.response_format)
    return payload


def canonical_payload_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def request_record(
    payload: Mapping[str, Any],
    *,
    endpoint: str,
    privacy_mode: PrivacyMode = PrivacyMode.REDACTED,
) -> ProviderRequestRecord:
    body = canonical_payload_bytes(payload)
    return ProviderRequestRecord(
        endpoint=endpoint,
        method="POST",
        sent_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        payload_sha256=hashlib.sha256(body).hexdigest(),
        redacted_payload=redact_value(payload, privacy_mode),
    )


def redact_value(value: Any, mode: PrivacyMode) -> Any:
    if isinstance(value, str):
        return store_text(value, mode)
    if isinstance(value, Mapping):
        return {str(key): redact_value(item, mode) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item, mode) for item in value]
    if isinstance(value, tuple):
        return [redact_value(item, mode) for item in value]
    return value


def normalize_role(role: str) -> str:
    if role in {"human", "user"}:
        return "user"
    if role in {"ai", "assistant"}:
        return "assistant"
    if role in {"system", "tool"}:
        return role
    return "user"
