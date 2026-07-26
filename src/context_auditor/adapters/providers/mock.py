"""Deterministic provider used by tests and controlled experiments."""

from __future__ import annotations

from context_auditor.domain.models import Message, ProviderResponse, ProviderUsage


class MockProvider:
    provider_name = "mock"

    def __init__(self, model: str = "mock-llm") -> None:
        self.model = model

    def invoke(self, messages: tuple[Message, ...]) -> ProviderResponse:
        user = next((item.content for item in reversed(messages) if item.role == "user"), "")
        content = f"mock response to: {user}"
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
        )
