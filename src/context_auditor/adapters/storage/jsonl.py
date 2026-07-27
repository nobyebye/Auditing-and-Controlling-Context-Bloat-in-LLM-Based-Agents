"""Append-only JSONL trace repository."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from context_auditor.domain.models import (
    AuditTrace,
    CounterfactualOutcome,
    GenerationParameters,
    Message,
    MitigationDecision,
    ModelRequestEnvelope,
    ProviderRequestRecord,
    ProviderUsage,
    READABLE_SCHEMA_VERSIONS,
    ReferenceAnnotation,
    ScoringResult,
    TextSegment,
    ToolDefinition,
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
    schema_version = data["schema_version"]
    if schema_version not in READABLE_SCHEMA_VERSIONS:
        raise ValueError(f"Unsupported trace schema version: {schema_version}")
    usage = data.get("provider_usage")
    generation = data.get("generation_parameters")
    scoring = data.get("scoring")
    envelope = envelope_from_dict(data.get("request_envelope"))
    provider_request = data.get("provider_request")
    legacy_ground_truth = {
        key: tuple(labels)
        for key, labels in data.get("ground_truth_labels", {}).items()
    }
    injected_labels = {
        key: tuple(labels)
        for key, labels in data.get("injected_labels", {}).items()
    }
    if schema_version == "1.1.0" and not injected_labels:
        injected_labels = legacy_ground_truth
    return AuditTrace(
        schema_version=schema_version,
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
        dataset_split=data.get("dataset_split", "all"),
        analysis_cohort=data.get("analysis_cohort", "primary"),
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
        request_envelope=envelope,
        provider_request=(
            ProviderRequestRecord(**provider_request) if provider_request else None
        ),
        framework_capture_hash=data.get("framework_capture_hash"),
        provider_payload_hash=data.get("provider_payload_hash"),
        evidence_tier=data.get(
            "evidence_tier",
            "controlled" if schema_version == "1.1.0" else "natural",
        ),
        parent_trace_id=data.get("parent_trace_id"),
        intervention=data.get("intervention", {}),
        risk_flags=tuple(data.get("risk_flags", [])),
        mitigation_decisions=tuple(
            MitigationDecision(**item) for item in data.get("mitigation_decisions", [])
        ),
        task_success=data.get("task_success"),
        task_output=data.get("task_output"),
        expected_answer=data.get("expected_answer"),
        provider_usage=ProviderUsage(**usage) if usage else None,
        latency_ms=data.get("latency_ms"),
        attempt_index=int(data.get("attempt_index", 0)),
        generation_parameters=(
            GenerationParameters(**generation) if generation else GenerationParameters()
        ),
        randomization_seed=data.get("randomization_seed"),
        replicate_id=data.get("replicate_id"),
        provider_seed=data.get("provider_seed"),
        injected_labels=injected_labels,
        ground_truth_labels=legacy_ground_truth,
        detected_labels={
            key: tuple(labels)
            for key, labels in data.get("detected_labels", {}).items()
        },
        reference_annotations=tuple(
            ReferenceAnnotation(
                **{
                    **item,
                    "reasons": tuple(item.get("reasons", ())),
                }
            )
            for item in data.get("reference_annotations", [])
        ),
        counterfactual_outcomes=tuple(
            CounterfactualOutcome(
                **{
                    **item,
                    "removed_segment_ids": tuple(item.get("removed_segment_ids", ())),
                }
            )
            for item in data.get("counterfactual_outcomes", [])
        ),
        scoring=ScoringResult(**scoring) if scoring else None,
    )


def envelope_from_dict(data: dict | None) -> ModelRequestEnvelope | None:
    if not data:
        return None
    generation = data.get("generation_parameters")
    return ModelRequestEnvelope(
        messages=tuple(Message(**item) for item in data.get("messages", [])),
        system_instructions=tuple(data.get("system_instructions", [])),
        tools=tuple(ToolDefinition(**item) for item in data.get("tools", [])),
        generation_parameters=(
            GenerationParameters(**generation) if generation else GenerationParameters()
        ),
        response_format=data.get("response_format", {}),
        randomization_seed=data.get("randomization_seed"),
        replicate_id=data.get("replicate_id"),
        provider_seed=data.get("provider_seed"),
        metadata=data.get("metadata", {}),
    )
