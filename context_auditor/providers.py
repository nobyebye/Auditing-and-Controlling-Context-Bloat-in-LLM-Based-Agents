"""Minimal chat provider abstraction for future real-model experiments."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol
from urllib import request

from .schema import Message


class ChatProvider(Protocol):
    provider_name: str
    model: str

    def complete(self, messages: list[Message]) -> str:
        """Return a model answer for model-visible messages."""


@dataclass(frozen=True)
class MockChatProvider:
    model: str = "mock-llm"
    provider_name: str = "mock"

    def complete(self, messages: list[Message]) -> str:
        user_messages = [message.content for message in messages if message.role == "user"]
        return f"mock response to: {user_messages[-1] if user_messages else ''}"


@dataclass(frozen=True)
class OpenAICompatibleChatProvider:
    model: str
    base_url: str
    api_key: str
    provider_name: str = "openai-compatible"
    timeout_seconds: int = 60

    def complete(self, messages: list[Message]) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": _normalize_role(message.role), "content": message.content}
                for message in messages
                if message.role != "tool"
            ],
        }
        req = request.Request(
            self.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"]


def provider_from_environment(provider_name: str, model: str) -> ChatProvider:
    if provider_name == "mock":
        return MockChatProvider(model=model)
    if provider_name == "openai-compatible":
        api_key = os.environ["OPENAI_COMPATIBLE_API_KEY"]
        base_url = os.environ.get("OPENAI_COMPATIBLE_BASE_URL", "https://api.openai.com/v1")
        return OpenAICompatibleChatProvider(model=model, base_url=base_url, api_key=api_key)
    raise ValueError(f"Unsupported provider: {provider_name}")


def _normalize_role(role: str) -> str:
    if role in {"human", "user"}:
        return "user"
    if role in {"ai", "assistant"}:
        return "assistant"
    if role == "system":
        return "system"
    return "user"
