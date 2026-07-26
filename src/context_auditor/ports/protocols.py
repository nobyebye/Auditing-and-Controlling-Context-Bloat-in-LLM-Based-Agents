"""Protocols that isolate the application layer from infrastructure."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Protocol

from context_auditor.domain.models import AuditTrace, Message, ProviderResponse


class ChatProvider(Protocol):
    provider_name: str
    model: str

    def invoke(self, messages: tuple[Message, ...]) -> ProviderResponse: ...


class Tokenizer(Protocol):
    name: str

    def count(self, text: str) -> int: ...


class TraceRepository(Protocol):
    path: Path

    def append(self, trace: AuditTrace) -> None: ...

    def iter_traces(self) -> Iterable[AuditTrace]: ...


class DatasetRepository(Protocol):
    def load(self, dataset_name: str, version: str) -> dict[str, Any]: ...

    def content_hash(self, dataset_name: str, version: str) -> str: ...


class Clock(Protocol):
    def now_iso(self) -> str: ...


class IdGenerator(Protocol):
    def new_trace_id(self) -> str: ...

    def new_run_id(
        self,
        framework: str,
        model: str,
        dataset_version: str,
        git_commit: str,
    ) -> str: ...
