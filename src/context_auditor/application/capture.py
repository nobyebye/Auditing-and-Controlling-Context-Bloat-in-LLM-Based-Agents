"""Capture model-visible context before a provider invocation."""

from __future__ import annotations

from dataclasses import replace

from context_auditor.analytics import compute_metrics
from context_auditor.domain.enums import SourceType
from context_auditor.domain.models import AuditTrace, CaptureRequest, Message, SCHEMA_VERSION
from context_auditor.domain.text import store_text
from context_auditor.ports import Clock, IdGenerator, Tokenizer, TraceRepository

from .segmentation import segment_messages


class CaptureContext:
    def __init__(
        self,
        repository: TraceRepository,
        tokenizer: Tokenizer,
        clock: Clock,
        ids: IdGenerator,
        source_dominance_threshold: float = 0.65,
    ) -> None:
        self.repository = repository
        self.tokenizer = tokenizer
        self.clock = clock
        self.ids = ids
        self.source_dominance_threshold = source_dominance_threshold
        self._previous_tokens: dict[tuple[str, str, str, int], int] = {}

    def execute(self, request: CaptureRequest) -> AuditTrace:
        segments = segment_messages(request.messages, self.tokenizer, request.privacy_mode)
        metrics = compute_metrics(segments)
        safe_messages = tuple(
            replace(message, content=store_text(message.content, request.privacy_mode))
            for message in request.messages
        )
        growth_key = (
            request.run_id,
            request.task_id,
            request.configuration,
            request.repetition_id,
        )
        previous_tokens = self._previous_tokens.get(growth_key)
        risk_flags = self._risk_flags(metrics, previous_tokens)
        self._previous_tokens[growth_key] = int(metrics["total_tokens"])
        trace = AuditTrace(
            schema_version=SCHEMA_VERSION,
            trace_id=self.ids.new_trace_id(),
            timestamp=self.clock.now_iso(),
            experiment_id=request.experiment_id,
            run_id=request.run_id,
            task_id=request.task_id,
            framework=request.framework,
            provider=request.provider,
            model=request.model,
            configuration=request.configuration,
            workflow_family=request.workflow_family,
            dataset_name=request.dataset_name,
            dataset_version=request.dataset_version,
            repetition_id=request.repetition_id,
            seed=request.seed,
            invocation_index=request.invocation_index,
            config_hash=request.config_hash,
            privacy_mode=request.privacy_mode.value,
            messages=safe_messages,
            segments=segments,
            metrics=metrics,
            risk_flags=risk_flags,
            mitigation_decisions=request.mitigation_decisions,
            task_success=request.task_success,
            task_output=store_text(request.task_output, request.privacy_mode) if request.task_output else None,
            expected_answer=request.expected_answer,
            provider_usage=request.provider_usage,
            latency_ms=request.latency_ms,
        )
        self.repository.append(trace)
        return trace

    def _risk_flags(self, metrics: dict, previous_tokens: int | None) -> tuple[str, ...]:
        flags: list[str] = []
        if previous_tokens and metrics["total_tokens"] > previous_tokens * 1.5:
            flags.append("context_growth_spike")
        if metrics["duplicate_segment_count"]:
            flags.append("duplicate_segments")
        for source, ratio in metrics["source_ratios"].items():
            if source not in {SourceType.SYSTEM.value, SourceType.USER.value} and ratio >= self.source_dominance_threshold:
                flags.append(f"source_dominance:{source}")
        return tuple(flags)
