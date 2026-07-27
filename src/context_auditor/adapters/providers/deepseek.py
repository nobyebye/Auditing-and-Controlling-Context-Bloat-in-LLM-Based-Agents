"""DeepSeek OpenAI-compatible provider with usage and latency capture."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from urllib import request

from context_auditor.domain.models import (
    GenerationParameters,
    ModelRequestEnvelope,
    ProviderResponse,
    ProviderUsage,
    ToolCall,
)

from .payload import build_openai_payload, canonical_payload_bytes, request_record

@dataclass(frozen=True)
class DeepSeekProvider:
    model: str
    api_key: str = field(repr=False)
    base_url: str = "https://api.deepseek.com"
    timeout_seconds: int = 90
    temperature: float = 0.0
    max_output_tokens: int = 256
    provider_name: str = "deepseek"

    @classmethod
    def from_environment(
        cls,
        model: str,
        generation: GenerationParameters | None = None,
    ) -> "DeepSeekProvider":
        selected = generation or GenerationParameters()
        return cls(
            model=model,
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            timeout_seconds=selected.timeout_seconds,
            temperature=selected.temperature,
            max_output_tokens=selected.max_output_tokens,
        )

    def invoke(self, envelope: ModelRequestEnvelope) -> ProviderResponse:
        payload = build_openai_payload(envelope, self.model)
        endpoint = self.base_url.rstrip("/") + "/chat/completions"
        record = request_record(payload, endpoint=endpoint)
        api_request = request.Request(
            endpoint,
            data=canonical_payload_bytes(payload),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started = time.perf_counter()
        with request.urlopen(api_request, timeout=self.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
        latency_ms = (time.perf_counter() - started) * 1000
        usage = body.get("usage", {})
        prompt_details = usage.get("prompt_tokens_details") or {}
        provider_usage = ProviderUsage(
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            cached_input_tokens=prompt_details.get("cached_tokens"),
        )
        provider_usage = ProviderUsage(
            **{
                **provider_usage.__dict__,
                "cost_usd": estimate_cost_usd(self.model, provider_usage),
            }
        )
        response_message = body["choices"][0]["message"]
        return ProviderResponse(
            content=response_message.get("content") or "",
            usage=provider_usage,
            latency_ms=latency_ms,
            response_id=body.get("id"),
            request_record=record,
            tool_calls=tuple(
                ToolCall(
                    call_id=str(item.get("id", "")),
                    name=str(item.get("function", {}).get("name", "")),
                    arguments=parse_tool_arguments(
                        item.get("function", {}).get("arguments", {})
                    ),
                )
                for item in response_message.get("tool_calls", [])
            ),
        )


def parse_tool_arguments(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value or "{}")
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Provider returned invalid tool-call arguments")


def estimate_cost_usd(model: str, usage: ProviderUsage) -> float | None:
    pricing = {
        "deepseek-v4-flash": (0.0028, 0.14, 0.28),
        "deepseek-v4-pro": (0.003625, 0.435, 0.87),
    }.get(model)
    if pricing is None or usage.input_tokens is None or usage.output_tokens is None:
        return None
    cached = usage.cached_input_tokens or 0
    uncached = max(0, usage.input_tokens - cached)
    cache_hit_price, cache_miss_price, output_price = pricing
    return (
        cached * cache_hit_price
        + uncached * cache_miss_price
        + usage.output_tokens * output_price
    ) / 1_000_000
