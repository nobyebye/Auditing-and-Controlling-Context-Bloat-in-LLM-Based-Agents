"""Strict LangChain adapter; no local fallback masquerades as LangChain."""

from __future__ import annotations

import importlib.util
from typing import Any, Callable

from context_auditor.domain.models import AuditTrace, CaptureRequest, Message, ToolCall

if importlib.util.find_spec("langchain_core") is not None:
    from langchain_core.callbacks import BaseCallbackHandler
else:
    class BaseCallbackHandler:  # type: ignore[no-redef]
        """Import-safe placeholder; construction still fails without LangChain."""


def langchain_available() -> bool:
    return importlib.util.find_spec("langchain_core") is not None


class LangChainContextAdapter:
    def __init__(self) -> None:
        if not langchain_available():
            raise RuntimeError(
                "langchain-core is required for the LangChain adapter; install the langchain extra"
            )

    def convert(self, messages: list[Any]) -> tuple[Message, ...]:
        return tuple(self._convert_one(item) for item in messages)

    @staticmethod
    def _convert_one(message: Any) -> Message:
        role = getattr(message, "type", None) or getattr(message, "role", None)
        content = getattr(message, "content", None)
        if role is None or content is None:
            raise TypeError(f"Unsupported LangChain message: {type(message).__name__}")
        additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
        metadata = {"raw_type": type(message).__name__, **dict(additional_kwargs)}
        raw_tool_calls = getattr(message, "tool_calls", ()) or ()
        return Message(
            role=normalize_langchain_role(str(role)),
            content=str(content),
            name=getattr(message, "name", None),
            metadata=metadata,
            tool_call_id=getattr(message, "tool_call_id", None),
            tool_calls=tuple(
                ToolCall(
                    call_id=str(item.get("id", "")),
                    name=str(item.get("name", "")),
                    arguments=dict(item.get("args", {})),
                )
                for item in raw_tool_calls
            ),
        )


class LangChainCaptureCallback(BaseCallbackHandler):
    """Capture the exact BaseMessage batches presented to a LangChain chat model."""

    def __init__(
        self,
        capture_use_case: Any,
        request_factory: Callable[[tuple[Message, ...]], CaptureRequest],
    ) -> None:
        if not langchain_available():
            raise RuntimeError(
                "langchain-core is required for the LangChain callback adapter"
            )
        super().__init__()
        self.capture_use_case = capture_use_case
        self.request_factory = request_factory
        self.adapter = LangChainContextAdapter()
        self.captured: list[AuditTrace] = []

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        **kwargs: Any,
    ) -> None:
        for batch in messages:
            converted = self.adapter.convert(batch)
            self.captured.append(
                self.capture_use_case.execute(self.request_factory(converted))
            )


def normalize_langchain_role(role: str) -> str:
    return {
        "human": "user",
        "ai": "assistant",
        "system": "system",
        "tool": "tool",
    }.get(role.casefold(), role.casefold())
