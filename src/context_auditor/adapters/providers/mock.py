"""Deterministic provider used by tests and controlled experiments."""

from __future__ import annotations

from context_auditor.domain.models import (
    ModelRequestEnvelope,
    ProviderResponse,
    ProviderUsage,
    ToolCall,
)

from .payload import build_openai_payload, request_record


class MockProvider:
    provider_name = "mock"

    def __init__(self, model: str = "mock-llm") -> None:
        self.model = model

    def invoke(self, request: ModelRequestEnvelope) -> ProviderResponse:
        messages = request.messages
        user = next((item.content for item in reversed(messages) if item.role == "user"), "")
        useful = next(
            (
                item.content
                for item in reversed(messages)
                if item.metadata.get("source_type") in {"tool", "retrieval", "memory"}
                and not item.metadata.get("bloat_labels")
            ),
            "",
        )
        content = useful or f"mock response to: {user}"
        has_tool_result = any(item.role == "tool" for item in messages)
        tool_calls = (
            (
                ToolCall(
                    call_id="mock-tool-call",
                    name=request.tools[0].name,
                    arguments={},
                ),
            )
            if request.tools and not has_tool_result
            else ()
        )
        input_tokens = sum(len(item.content.split()) for item in messages)
        output_tokens = len(content.split())
        return ProviderResponse(
            content=content,
            usage=ProviderUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
            latency_ms=0.0,
            response_id="mock-response",
            request_record=request_record(
                build_openai_payload(request, self.model),
                endpoint="mock://chat/completions",
            ),
            tool_calls=tool_calls,
        )
