"""Runtime auditor that creates and writes invocation traces."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .guard import ContextGrowthGuard
from .hashing import hash_text
from .metrics import compute_metrics
from .provenance import segment_messages
from .schema import SCHEMA_VERSION, AuditTrace, Message


@dataclass(frozen=True)
class TraceMetadata:
    task_id: str
    framework: str
    provider: str
    model: str
    configuration: str
    workflow_family: str
    experiment_id: str = "pilot"
    run_id: str = "run-001"
    dataset_name: str = "controlled_synthetic"
    config: dict | None = None

    @property
    def config_hash(self) -> str:
        payload = json.dumps(self.config or {"configuration": self.configuration}, sort_keys=True)
        return hash_text(payload)[:12]


class RuntimeAuditor:
    def __init__(
        self,
        output_path: str | Path | None = None,
        guard: ContextGrowthGuard | None = None,
        cost_per_1k_tokens: float = 0.0,
    ) -> None:
        self.output_path = Path(output_path) if output_path else None
        self.guard = guard or ContextGrowthGuard()
        self.cost_per_1k_tokens = cost_per_1k_tokens
        self._invocation_by_task: dict[str, int] = {}

    def capture(
        self,
        metadata: TraceMetadata,
        messages: list[Message],
        task_success: bool | None = None,
        task_output: str | None = None,
    ) -> AuditTrace:
        invocation_index = self._invocation_by_task.get(metadata.task_id, 0)
        self._invocation_by_task[metadata.task_id] = invocation_index + 1

        segments = segment_messages(messages)
        metrics = compute_metrics(segments, self.cost_per_1k_tokens)
        trace = AuditTrace(
            schema_version=SCHEMA_VERSION,
            trace_id=str(uuid4()),
            experiment_id=metadata.experiment_id,
            run_id=metadata.run_id,
            task_id=metadata.task_id,
            framework=metadata.framework,
            provider=metadata.provider,
            model=metadata.model,
            configuration=metadata.configuration,
            config_hash=metadata.config_hash,
            dataset_name=metadata.dataset_name,
            workflow_family=metadata.workflow_family,
            invocation_index=invocation_index,
            timestamp=datetime.now(UTC).isoformat(),
            messages=messages,
            segments=segments,
            metrics=metrics,
            task_success=task_success,
            task_output=task_output,
            risk_flags=[],
        )
        trace.risk_flags = self.guard.evaluate(trace)
        self.write(trace)
        return trace

    def write(self, trace: AuditTrace) -> None:
        if not self.output_path:
            return
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(trace.to_dict(), ensure_ascii=False) + "\n")
