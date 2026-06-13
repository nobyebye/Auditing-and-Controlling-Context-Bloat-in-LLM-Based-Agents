"""JSONL trace input/output helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .schema import AuditTrace, Message, Segment


def trace_from_dict(data: dict) -> AuditTrace:
    messages = [Message(**message) for message in data.get("messages", [])]
    segments = [Segment(**segment) for segment in data.get("segments", [])]
    return AuditTrace(
        schema_version=data.get("schema_version", "0.1.0"),
        trace_id=data["trace_id"],
        experiment_id=data.get("experiment_id", "unknown"),
        run_id=data.get("run_id", "unknown"),
        task_id=data["task_id"],
        framework=data["framework"],
        provider=data["provider"],
        model=data["model"],
        configuration=data["configuration"],
        config_hash=data.get("config_hash", ""),
        dataset_name=data.get("dataset_name", "unknown"),
        workflow_family=data["workflow_family"],
        invocation_index=data["invocation_index"],
        timestamp=data["timestamp"],
        messages=messages,
        segments=segments,
        metrics=data.get("metrics", {}),
        task_success=data.get("task_success"),
        task_output=data.get("task_output"),
        risk_flags=data.get("risk_flags", []),
    )


def load_jsonl(path: str | Path) -> list[AuditTrace]:
    trace_path = Path(path)
    with trace_path.open(encoding="utf-8") as handle:
        return [trace_from_dict(json.loads(line)) for line in handle if line.strip()]


def write_jsonl(path: str | Path, traces: Iterable[AuditTrace]) -> None:
    trace_path = Path(path)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("w", encoding="utf-8") as handle:
        for trace in traces:
            handle.write(json.dumps(trace.to_dict(), ensure_ascii=False) + "\n")
