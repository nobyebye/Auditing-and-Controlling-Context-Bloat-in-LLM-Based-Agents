"""Pinned LLMLingua-2 baseline with protected agent-control content."""

from __future__ import annotations

from dataclasses import dataclass, replace
import inspect
import json
import math
from typing import Any

from context_auditor.adapters.common import RegexTokenizer
from context_auditor.application.segmentation import label_source
from context_auditor.domain.enums import SourceType
from context_auditor.domain.models import Message

DEFAULT_MODEL = "microsoft/llmlingua-2-xlm-roberta-large-meetingbank"
DEFAULT_MODEL_REVISION = "ebaba9b0e874dadd3003ffcff828e4397e568089"


@dataclass(frozen=True)
class CompressionOutcome:
    messages: tuple[Message, ...]
    target_managed_tokens: int
    actual_managed_tokens: int
    tolerance_tokens: int
    within_tolerance: bool
    requested_target_tokens: int


class DeterministicCompressionBackend:
    """Small offline backend used only by mock E2E tests."""

    def compress_prompt_llmlingua2(self, context, target_token, **_kwargs):
        text = " ".join(str(item) for item in context)
        words = text.split()
        return {"compressed_prompt": " ".join(words[: max(1, target_token)])}


class LLMLingua2Compressor:
    MANAGED_SOURCES = frozenset(
        {SourceType.RETRIEVAL, SourceType.MEMORY, SourceType.TOOL}
    )

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        model_revision: str = DEFAULT_MODEL_REVISION,
        backend: Any | None = None,
        tokenizer: Any | None = None,
        device: str = "cpu",
    ) -> None:
        self.model_name = model_name
        self.model_revision = model_revision
        self.device = device
        self._backend = backend
        self._tokenizer = tokenizer or (
            RegexTokenizer() if backend is not None else None
        )

    def compress(
        self,
        messages: tuple[Message, ...],
        *,
        target_tokens: int,
    ) -> CompressionOutcome:
        if target_tokens < 1:
            raise ValueError("LLMLingua-2 target_tokens must be positive")
        managed = self._managed(messages)
        if not managed:
            return CompressionOutcome(
                messages=messages,
                target_managed_tokens=target_tokens,
                actual_managed_tokens=0,
                tolerance_tokens=token_tolerance(target_tokens),
                within_tolerance=False,
                requested_target_tokens=0,
            )
        original_tokens = self.count_managed(messages)
        if original_tokens <= target_tokens:
            return CompressionOutcome(
                messages=messages,
                target_managed_tokens=target_tokens,
                actual_managed_tokens=original_tokens,
                tolerance_tokens=token_tolerance(target_tokens),
                within_tolerance=(
                    abs(original_tokens - target_tokens)
                    <= token_tolerance(target_tokens)
                ),
                requested_target_tokens=original_tokens,
            )
        backend = self._backend or self._load_backend()
        lower = 1
        upper = max(1, sum(self.count_text(item.content) for _, item in managed))
        candidates: list[tuple[int, int, tuple[Message, ...]]] = []
        visited: set[int] = set()
        while lower <= upper and len(visited) < 16:
            requested = (lower + upper) // 2
            if requested in visited:
                break
            visited.add(requested)
            candidate = self._compress_once(
                messages,
                requested_target=requested,
                backend=backend,
            )
            observed = self.count_managed(candidate)
            candidates.append((abs(observed - target_tokens), requested, candidate))
            if observed < target_tokens:
                lower = requested + 1
            elif observed > target_tokens:
                upper = requested - 1
            else:
                break
        _difference, requested, best = min(
            candidates,
            key=lambda item: (item[0], item[1]),
        )
        actual = self.count_managed(best)
        tolerance = token_tolerance(target_tokens)
        return CompressionOutcome(
            messages=best,
            target_managed_tokens=target_tokens,
            actual_managed_tokens=actual,
            tolerance_tokens=tolerance,
            within_tolerance=abs(actual - target_tokens) <= tolerance,
            requested_target_tokens=requested,
        )

    def count_managed(self, messages: tuple[Message, ...]) -> int:
        managed_payload = [
            {
                "role": message.role,
                "name": message.name,
                "content": message.content,
            }
            for _index, message in self._managed(messages)
        ]
        serialized = json.dumps(
            managed_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return self.count_text(serialized)

    def count_text(self, text: str) -> int:
        tokenizer = self._tokenizer or self._load_tokenizer()
        if isinstance(tokenizer, RegexTokenizer):
            return tokenizer.count(text)
        return len(tokenizer.encode(text, add_special_tokens=False))

    def _compress_once(
        self,
        messages: tuple[Message, ...],
        *,
        requested_target: int,
        backend: Any,
    ) -> tuple[Message, ...]:
        managed = self._managed(messages)
        content_tokens = [
            max(1, self.count_text(message.content))
            for _, message in managed
        ]
        total = sum(content_tokens)
        result = list(messages)
        remaining = requested_target
        for position, ((index, message), source_tokens) in enumerate(
            zip(managed, content_tokens)
        ):
            if position == len(managed) - 1:
                budget = max(1, remaining)
            else:
                budget = max(1, round(requested_target * source_tokens / total))
                remaining -= budget
            options = {
                "context": [message.content],
                "target_token": budget,
                "use_context_level_filter": False,
                "use_token_level_filter": True,
                "force_reserve_digit": False,
                "drop_consecutive": False,
            }
            supported = inspect.signature(
                backend.compress_prompt_llmlingua2
            ).parameters
            compressed = backend.compress_prompt_llmlingua2(
                **{
                    key: value
                    for key, value in options.items()
                    if key in supported
                }
            )["compressed_prompt"]
            result[index] = replace(
                message,
                content=compressed,
                metadata={
                    **message.metadata,
                    "compression_baseline": "llmlingua-2",
                    "llmlingua_model_revision": self.model_revision,
                },
            )
        return tuple(result)

    def _managed(
        self,
        messages: tuple[Message, ...],
    ) -> list[tuple[int, Message]]:
        return [
            (index, message)
            for index, message in enumerate(messages)
            if label_source(message) in self.MANAGED_SOURCES
        ]

    def _load_tokenizer(self):
        try:
            from transformers import AutoTokenizer
        except ImportError as error:
            raise RuntimeError(
                "LLMLingua-2 requires the frozen compression dependencies"
            ) from error
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_name,
            revision=self.model_revision,
        )
        return self._tokenizer

    def _load_backend(self) -> Any:
        try:
            import torch
            from llmlingua import PromptCompressor
        except ImportError as error:
            raise RuntimeError(
                "LLMLingua-2 is optional; install the 'compression' extra"
            ) from error
        self._backend = PromptCompressor(
            model_name=self.model_name,
            device_map=self.device,
            model_config={
                "revision": self.model_revision,
                "torch_dtype": torch.float32,
            },
            use_llmlingua2=True,
            llmlingua2_config={
                "max_batch_size": 50,
                "max_force_token": 100,
            },
        )
        if self._tokenizer is None:
            self._tokenizer = self._backend.tokenizer
        return self._backend


def token_tolerance(target_tokens: int) -> int:
    return max(2, math.ceil(target_tokens * 0.02))
