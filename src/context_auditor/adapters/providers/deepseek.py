"""DeepSeek OpenAI-compatible provider with usage and latency capture."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from urllib import request

from context_auditor.domain.models import Message, ProviderResponse, ProviderUsage


@dataclass(frozen=True)
class DeepSeekProvider:
    model: str
    api_key: str = field(repr=False)
    base_url: str = "https://api.deepseek.com"
    timeout_seconds: int = 90
    provider_name: str = "deepseek"

    @classmethod
    def from_environment(cls, model: str) -> "DeepSeekProvider":
        return cls(
            model=model,
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )

    def invoke(self, messages: tuple[Message, ...]) -> ProviderResponse:
        payload = {
            "model": self.model,
            "messages": [
                {"role": normalize_role(item.role), "content": item.content}
                for item in messages
            ],
            "stream": False,
        }
        api_request = request.Request(
            self.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
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
        return ProviderResponse(
            content=body["choices"][0]["message"]["content"],
            usage=provider_usage,
            latency_ms=latency_ms,
            response_id=body.get("id"),
        )


def normalize_role(role: str) -> str:
    if role in {"human", "user"}:
        return "user"
    if role in {"ai", "assistant"}:
        return "assistant"
    if role == "system":
        return "system"
    if role == "tool":
        return "tool"
    return "user"


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
