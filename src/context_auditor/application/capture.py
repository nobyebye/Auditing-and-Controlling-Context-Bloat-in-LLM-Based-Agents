"""Capture model-visible context before a provider invocation."""

from __future__ import annotations

from dataclasses import replace

from context_auditor.analytics import compute_metrics
from context_auditor.domain.enums import SourceType
from context_auditor.domain.models import AuditTrace, CaptureRequest, Message, SCHEMA_VERSION
from context_auditor.domain.text import store_text
from context_auditor.ports import Clock, IdGenerator, Tokenizer, TraceRepository

from .segmentation import segment_messages
from .localization import findings_by_segment, localize_segments


class CaptureContext:
    def __init__(
        self,
        repository: TraceRepository,
        tokenizer: Tokenizer,
        clock: Clock,
        ids: IdGenerator,
        source_dominance_threshold: float = 0.65,
        near_duplicate_threshold: float = 0.8,
        relevance_threshold: float = 0.05,
        verbose_tool_token_threshold: int = 80,
    ) -> None:
        self.repository = repository
        self.tokenizer = tokenizer
        self.clock = clock
        self.ids = ids
        self.source_dominance_threshold = source_dominance_threshold
        self.near_duplicate_threshold = near_duplicate_threshold
        self.relevance_threshold = relevance_threshold
        self.verbose_tool_token_threshold = verbose_tool_token_threshold
        self._previous_tokens: dict[tuple[str, str, str, int], int] = {}

    def execute(self, request: CaptureRequest) -> AuditTrace:
        segments = segment_messages(request.messages, self.tokenizer, request.privacy_mode)
        metrics = compute_metrics(segments)
        user_query = next(
            (message.content for message in reversed(request.messages) if message.role == "user"),
            "",
        )
        detected_labels = request.detected_labels or findings_by_segment(
            localize_segments(
                segments,
                user_query,
                near_duplicate_threshold=self.near_duplicate_threshold,
                relevance_threshold=self.relevance_threshold,
                verbose_tool_token_threshold=self.verbose_tool_token_threshold,
            )
        )
        ground_truth_labels = request.ground_truth_labels or ground_truth_from_messages(
            request.messages, segments
        )
        ground_truth_ids = set(ground_truth_labels)
        detected_ids = set(detected_labels)
        ground_truth_tokens = sum(
            segment.token_count for segment in segments if segment.segment_id in ground_truth_ids
        )
        detected_tokens = sum(
            segment.token_count for segment in segments if segment.segment_id in detected_ids
        )
        total_tokens = int(metrics["total_tokens"])
        metrics = {
            **metrics,
            "ground_truth_bloat_tokens": ground_truth_tokens,
            "ground_truth_bloat_ratio": (
                ground_truth_tokens / total_tokens if total_tokens else 0.0
            ),
            "detected_bloat_tokens": detected_tokens,
            "detected_bloat_ratio": (
                detected_tokens / total_tokens if total_tokens else 0.0
            ),
        }
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
            dataset_split=request.dataset_split,
            analysis_cohort=request.analysis_cohort,
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
            attempt_index=request.attempt_index,
            generation_parameters=request.generation_parameters,
            ground_truth_labels=ground_truth_labels,
            detected_labels=detected_labels,
            scoring=request.scoring,
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


def ground_truth_from_messages(
    messages: tuple[Message, ...],
    segments: tuple,
) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for segment in segments:
        raw = messages[segment.message_index].metadata.get("bloat_labels", ())
        labels = (raw,) if isinstance(raw, str) else tuple(str(label) for label in raw)
        if labels:
            result[segment.segment_id] = labels
    return result
