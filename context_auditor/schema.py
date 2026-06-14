"""Dataclasses for the public trace schema."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = "0.8.0"


@dataclass
class Message:
    role: str
    content: str
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Segment:
    segment_id: str
    message_index: int
    role: str
    source_type: str
    text: str
    char_count: int
    token_count: int
    content_hash: str
    normalized_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AuditTrace:
    schema_version: str
    trace_id: str
    experiment_id: str
    run_id: str
    task_id: str
    framework: str
    provider: str
    model: str
    configuration: str
    config_hash: str
    dataset_name: str
    workflow_family: str
    invocation_index: int
    timestamp: str
    messages: list[Message]
    segments: list[Segment]
    metrics: dict[str, Any]
    task_success: bool | None = None
    task_output: str | None = None
    task_expected_keyword: str | None = None
    risk_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["messages"] = [message.to_dict() for message in self.messages]
        data["segments"] = [segment.to_dict() for segment in self.segments]
        return data
