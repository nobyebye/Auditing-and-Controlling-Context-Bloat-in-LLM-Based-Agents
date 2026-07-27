"""Capture model-visible context before a provider invocation."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from context_auditor.analytics import compute_metrics
from context_auditor.domain.enums import SourceType
from context_auditor.domain.models import (
    AuditTrace,
    CaptureRequest,
    Message,
    ModelRequestEnvelope,
    SCHEMA_VERSION,
    ToolDefinition,
)
from context_auditor.domain.text import store_text
from context_auditor.ports import Clock, IdGenerator, Tokenizer, TraceRepository

from .segmentation import segment_envelope
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
        validate_evidence_boundary(request)
        envelope = request.request_envelope or ModelRequestEnvelope(
            messages=request.messages,
            generation_parameters=request.generation_parameters,
        )
        segments = segment_envelope(
            envelope,
            self.tokenizer,
            request.privacy_mode,
        )
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
        injected_labels = (
            request.injected_labels
            or request.ground_truth_labels
            or (
                injected_labels_from_messages(request.messages, segments)
                if request.evidence_tier == "controlled"
                else {}
            )
        )
        injected_ids = set(injected_labels)
        detected_ids = set(detected_labels)
        injected_tokens = sum(
            segment.token_count for segment in segments if segment.segment_id in injected_ids
        )
        reference_remove_ids = {
            annotation.segment_id
            for annotation in request.reference_annotations
            if annotation.adjudicated and annotation.decision == "remove"
        }
        reference_tokens = sum(
            segment.token_count
            for segment in segments
            if segment.segment_id in reference_remove_ids
        )
        detected_tokens = sum(
            segment.token_count for segment in segments if segment.segment_id in detected_ids
        )
        total_tokens = int(metrics["total_tokens"])
        metrics = {
            **metrics,
            "injected_bloat_tokens": injected_tokens,
            "injected_bloat_ratio": (
                injected_tokens / total_tokens if total_tokens else 0.0
            ),
            "human_reference_bloat_tokens": reference_tokens,
            "human_reference_bloat_ratio": (
                reference_tokens / total_tokens if total_tokens else 0.0
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
        safe_envelope = redact_envelope(envelope, request)
        safe_provider_request = (
            replace(
                request.provider_request,
                redacted_payload=redact_mapping(
                    request.provider_request.redacted_payload,
                    request,
                ),
            )
            if request.provider_request
            else None
        )
        growth_key = (
            request.run_id,
            request.task_id,
            request.configuration,
            request.repetition_id,
        )
        previous_tokens = self._previous_tokens.get(growth_key)
        risk_flags = self._risk_flags(metrics, previous_tokens)
        if (
            request.framework_capture_hash
            and request.provider_request
            and request.framework_capture_hash
            != request.provider_request.payload_sha256
        ):
            risk_flags = (*risk_flags, "payload_mismatch")
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
            request_envelope=safe_envelope,
            provider_request=safe_provider_request,
            framework_capture_hash=request.framework_capture_hash,
            provider_payload_hash=(
                request.provider_request.payload_sha256
                if request.provider_request
                else None
            ),
            randomization_seed=envelope.randomization_seed,
            replicate_id=envelope.replicate_id,
            provider_seed=envelope.provider_seed,
            evidence_tier=request.evidence_tier,
            parent_trace_id=request.parent_trace_id,
            intervention=request.intervention,
            risk_flags=risk_flags,
            mitigation_decisions=request.mitigation_decisions,
            task_success=request.task_success,
            task_output=store_text(request.task_output, request.privacy_mode) if request.task_output else None,
            expected_answer=request.expected_answer,
            provider_usage=request.provider_usage,
            latency_ms=request.latency_ms,
            attempt_index=request.attempt_index,
            generation_parameters=request.generation_parameters,
            injected_labels=injected_labels,
            detected_labels=detected_labels,
            reference_annotations=request.reference_annotations,
            counterfactual_outcomes=request.counterfactual_outcomes,
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


def injected_labels_from_messages(
    messages: tuple[Message, ...],
    segments: tuple,
) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for segment in segments:
        if segment.container_type != "message":
            continue
        raw = messages[segment.message_index].metadata.get("bloat_labels", ())
        labels = (raw,) if isinstance(raw, str) else tuple(str(label) for label in raw)
        if labels:
            result[segment.segment_id] = labels
    return result


def ground_truth_from_messages(
    messages: tuple[Message, ...],
    segments: tuple,
) -> dict[str, tuple[str, ...]]:
    """Compatibility alias for controlled schema-1.1 fixtures."""
    return injected_labels_from_messages(messages, segments)


def validate_evidence_boundary(request: CaptureRequest) -> None:
    if request.evidence_tier == "controlled":
        return
    if request.ground_truth_labels or request.injected_labels:
        raise ValueError(
            "Natural and counterfactual evidence cannot accept injected labels"
        )
    contaminated = [
        index
        for index, message in enumerate(request.messages)
        if message.metadata.get("bloat_labels")
    ]
    if contaminated:
        raise ValueError(
            "Natural and counterfactual evidence cannot contain bloat_labels "
            f"metadata; contaminated message indexes: {contaminated}"
        )


def redact_envelope(
    envelope: ModelRequestEnvelope,
    request: CaptureRequest,
) -> ModelRequestEnvelope:
    return replace(
        envelope,
        messages=tuple(
            replace(message, content=store_text(message.content, request.privacy_mode))
            for message in envelope.messages
        ),
        system_instructions=tuple(
            store_text(instruction, request.privacy_mode)
            for instruction in envelope.system_instructions
        ),
        tools=tuple(
            ToolDefinition(
                name=tool.name,
                description=store_text(
                    tool.description,
                    request.privacy_mode,
                ),
                parameters=redact_mapping(tool.parameters, request),
            )
            for tool in envelope.tools
        ),
        response_format=redact_mapping(envelope.response_format, request),
        metadata=redact_mapping(envelope.metadata, request),
    )


def redact_mapping(value: Mapping[str, Any], request: CaptureRequest) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, str):
            result[str(key)] = store_text(item, request.privacy_mode)
        elif isinstance(item, Mapping):
            result[str(key)] = redact_mapping(item, request)
        elif isinstance(item, (list, tuple)):
            result[str(key)] = [
                store_text(entry, request.privacy_mode)
                if isinstance(entry, str)
                else entry
                for entry in item
            ]
        else:
            result[str(key)] = item
    return result
