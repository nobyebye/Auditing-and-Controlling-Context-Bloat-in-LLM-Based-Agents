"""Optional LLMLingua-2 baseline with protected agent-control messages."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from context_auditor.adapters.common import RegexTokenizer
from context_auditor.application.segmentation import label_source
from context_auditor.domain.enums import SourceType
from context_auditor.domain.models import Message


class DeterministicCompressionBackend:
    """Small offline backend used only to exercise the Study C pipeline."""

    def compress_prompt_llmlingua2(self, context, target_token):
        text = " ".join(str(item) for item in context)
        words = text.split()
        return {"compressed_prompt": " ".join(words[: max(1, target_token)])}


class LLMLingua2Compressor:
    MANAGED_SOURCES = frozenset(
        {SourceType.RETRIEVAL, SourceType.MEMORY, SourceType.TOOL}
    )

    def __init__(
        self,
        model_name: str = "microsoft/llmlingua-2-xlm-roberta-large-meetingbank",
        backend: Any | None = None,
    ) -> None:
        self.model_name = model_name
        self.tokenizer = RegexTokenizer()
        self._backend = backend

    def compress(
        self,
        messages: tuple[Message, ...],
        *,
        target_tokens: int,
    ) -> tuple[Message, ...]:
        if target_tokens < 1:
            raise ValueError("LLMLingua-2 target_tokens must be positive")
        managed = [
            (index, message)
            for index, message in enumerate(messages)
            if label_source(message) in self.MANAGED_SOURCES
        ]
        if not managed:
            return messages
        original_tokens = sum(
            self.tokenizer.count(message.content) for _, message in managed
        )
        if original_tokens <= target_tokens:
            return messages
        backend = self._backend or self._load_backend()
        result = list(messages)
        remaining = target_tokens
        for position, (index, message) in enumerate(managed):
            source_tokens = self.tokenizer.count(message.content)
            if position == len(managed) - 1:
                budget = max(1, remaining)
            else:
                budget = max(
                    1,
                    round(target_tokens * source_tokens / original_tokens),
                )
                remaining -= budget
            compressed = backend.compress_prompt_llmlingua2(
                [message.content],
                target_token=budget,
            )["compressed_prompt"]
            result[index] = replace(
                message,
                content=compressed,
                metadata={
                    **message.metadata,
                    "compression_baseline": "llmlingua-2",
                },
            )
        return tuple(result)

    def _load_backend(self) -> Any:
        try:
            from llmlingua import PromptCompressor
        except ImportError as error:
            raise RuntimeError(
                "LLMLingua-2 is optional; install the 'compression' extra"
            ) from error
        self._backend = PromptCompressor(
            model_name=self.model_name,
            use_llmlingua2=True,
        )
        return self._backend
