"""Append-only JSONL trace repository."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from context_auditor.domain.models import (
    AuditTrace,
    Message,
    MitigationDecision,
    ProviderUsage,
    TextSegment,
)

from .serialization import dumps


class JsonlTraceRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, trace: AuditTrace) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(dumps(trace) + "\n")

    def iter_traces(self) -> Iterable[AuditTrace]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield trace_from_dict(json.loads(line))


def trace_from_dict(data: dict) -> AuditTrace:
    usage = data.get("provider_usage")
    return AuditTrace(
        schema_version=data["schema_version"],
        trace_id=data["trace_id"],
        timestamp=data["timestamp"],
        experiment_id=data["experiment_id"],
        run_id=data["run_id"],
        task_id=data["task_id"],
        framework=data["framework"],
        provider=data["provider"],
        model=data["model"],
        configuration=data["configuration"],
        workflow_family=data["workflow_family"],
        dataset_name=data["dataset_name"],
        dataset_version=data["dataset_version"],
        repetition_id=int(data["repetition_id"]),
        seed=int(data["seed"]),
        invocation_index=int(data["invocation_index"]),
        config_hash=data["config_hash"],
        privacy_mode=data["privacy_mode"],
        messages=tuple(Message(**item) for item in data.get("messages", [])),
        segments=tuple(TextSegment(**item) for item in data.get("segments", [])),
        metrics=data.get("metrics", {}),
        risk_flags=tuple(data.get("risk_flags", [])),
        mitigation_decisions=tuple(
            MitigationDecision(**item) for item in data.get("mitigation_decisions", [])
        ),
        task_success=data.get("task_success"),
        task_output=data.get("task_output"),
        expected_answer=data.get("expected_answer"),
        provider_usage=ProviderUsage(**usage) if usage else None,
        latency_ms=data.get("latency_ms"),
    )
