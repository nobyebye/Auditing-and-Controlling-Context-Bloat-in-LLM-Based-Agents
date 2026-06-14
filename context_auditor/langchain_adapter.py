"""Optional LangChain callback adapter.

This file avoids importing LangChain at module import time so the core thesis
artifact remains runnable without optional dependencies.
"""

from __future__ import annotations

from typing import Any

from .schema import Message
from .tracer import RuntimeAuditor, TraceMetadata


def convert_langchain_message(message: Any) -> Message:
    role = getattr(message, "type", None) or getattr(message, "role", "unknown")
    content = getattr(message, "content", "")
    return Message(role=_normalize_langchain_role(str(role)), content=str(content), metadata={"raw_type": type(message).__name__})


def _normalize_langchain_role(role: str) -> str:
    if role == "human":
        return "user"
    if role == "ai":
        return "assistant"
    return role


class AuditingLangChainCallback:
    def __init__(self, auditor: RuntimeAuditor, metadata: TraceMetadata) -> None:
        self.auditor = auditor
        self.metadata = metadata

    def on_chat_model_start(self, serialized: dict[str, Any], messages: list[list[Any]], **kwargs: Any) -> None:
        for batch in messages:
            converted = [convert_langchain_message(message) for message in batch]
            self.auditor.capture(self.metadata, converted)
