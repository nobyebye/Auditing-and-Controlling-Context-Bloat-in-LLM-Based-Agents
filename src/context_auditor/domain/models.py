"""Immutable domain models with no infrastructure dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .enums import PrivacyMode, RunStatus

SCHEMA_VERSION = "1.2.0"
READABLE_SCHEMA_VERSIONS = frozenset({"1.1.0", SCHEMA_VERSION})


@dataclass(frozen=True)
class Message:
    role: str
    content: str
    name: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelRequestEnvelope:
    messages: tuple[Message, ...]
    system_instructions: tuple[str, ...] = ()
    tools: tuple[ToolDefinition, ...] = ()
    generation_parameters: "GenerationParameters" = field(
        default_factory=lambda: GenerationParameters()
    )
    response_format: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderRequestRecord:
    endpoint: str
    method: str
    sent_at: str
    payload_sha256: str
    redacted_payload: Mapping[str, Any]
    payload_schema: str = "openai-chat-completions"


@dataclass(frozen=True)
class TextSegment:
    segment_id: str
    parent_message_id: str
    message_index: int
    ordinal: int
    role: str
    source_type: str
    text: str
    char_count: int
    token_count: int
    content_hash: str
    normalized_hash: str
    privacy_mode: str
    source_id: str | None = None
    relevance_score: float | None = None
    container_type: str = "message"
    container_index: int = 0


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    cost_usd: float | None = None


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResponse:
    content: str
    usage: ProviderUsage = field(default_factory=ProviderUsage)
    latency_ms: float | None = None
    response_id: str | None = None
    request_record: ProviderRequestRecord | None = None
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class GenerationParameters:
    temperature: float = 0.0
    max_output_tokens: int = 256
    timeout_seconds: int = 90
    max_retries: int = 3


@dataclass(frozen=True)
class ScoringResult:
    success: bool
    score: float
    method: str
    normalized_output: str
    normalized_expected: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MitigationDecision:
    segment_id: str
    action: str
    reason: str
    source_type: str
    removed_tokens: int


@dataclass(frozen=True)
class BloatFinding:
    segment_id: str
    source_type: str
    label: str
    score: float
    evidence_segment_id: str | None = None


@dataclass(frozen=True)
class ReferenceAnnotation:
    segment_id: str
    annotator_id: str
    decision: str
    reasons: tuple[str, ...] = ()
    confidence: int | None = None
    annotation_set_id: str = ""
    adjudicated: bool = False


@dataclass(frozen=True)
class CounterfactualOutcome:
    variant_id: str
    parent_trace_id: str
    removed_segment_ids: tuple[str, ...]
    seed: int
    task_success: bool
    task_score: float | None = None
    output_hash: str | None = None


@dataclass(frozen=True)
class CounterfactualVariant:
    variant_id: str
    parent_trace_id: str
    removed_segment_ids: tuple[str, ...]
    request: ModelRequestEnvelope
    variant_type: str


@dataclass(frozen=True)
class CaptureRequest:
    experiment_id: str
    run_id: str
    task_id: str
    framework: str
    provider: str
    model: str
    configuration: str
    workflow_family: str
    dataset_name: str
    dataset_version: str
    repetition_id: int
    seed: int
    invocation_index: int
    messages: tuple[Message, ...]
    config_hash: str
    request_envelope: ModelRequestEnvelope | None = None
    provider_request: ProviderRequestRecord | None = None
    framework_capture_hash: str | None = None
    evidence_tier: str = "controlled"
    parent_trace_id: str | None = None
    intervention: Mapping[str, Any] = field(default_factory=dict)
    dataset_split: str = "all"
    analysis_cohort: str = "primary"
    task_success: bool | None = None
    task_output: str | None = None
    expected_answer: str | None = None
    provider_usage: ProviderUsage | None = None
    latency_ms: float | None = None
    attempt_index: int = 0
    generation_parameters: GenerationParameters = field(default_factory=GenerationParameters)
    injected_labels: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    ground_truth_labels: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    detected_labels: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    reference_annotations: tuple[ReferenceAnnotation, ...] = ()
    counterfactual_outcomes: tuple[CounterfactualOutcome, ...] = ()
    scoring: ScoringResult | None = None
    mitigation_decisions: tuple[MitigationDecision, ...] = ()
    privacy_mode: PrivacyMode = PrivacyMode.REDACTED


@dataclass(frozen=True)
class AuditTrace:
    schema_version: str
    trace_id: str
    timestamp: str
    experiment_id: str
    run_id: str
    task_id: str
    framework: str
    provider: str
    model: str
    configuration: str
    workflow_family: str
    dataset_name: str
    dataset_version: str
    repetition_id: int
    seed: int
    invocation_index: int
    config_hash: str
    privacy_mode: str
    messages: tuple[Message, ...]
    segments: tuple[TextSegment, ...]
    metrics: Mapping[str, Any]
    request_envelope: ModelRequestEnvelope | None = None
    provider_request: ProviderRequestRecord | None = None
    framework_capture_hash: str | None = None
    provider_payload_hash: str | None = None
    evidence_tier: str = "controlled"
    parent_trace_id: str | None = None
    intervention: Mapping[str, Any] = field(default_factory=dict)
    dataset_split: str = "all"
    analysis_cohort: str = "primary"
    risk_flags: tuple[str, ...] = ()
    mitigation_decisions: tuple[MitigationDecision, ...] = ()
    task_success: bool | None = None
    task_output: str | None = None
    expected_answer: str | None = None
    provider_usage: ProviderUsage | None = None
    latency_ms: float | None = None
    attempt_index: int = 0
    generation_parameters: GenerationParameters = field(default_factory=GenerationParameters)
    injected_labels: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    ground_truth_labels: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    detected_labels: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    reference_annotations: tuple[ReferenceAnnotation, ...] = ()
    counterfactual_outcomes: tuple[CounterfactualOutcome, ...] = ()
    scoring: ScoringResult | None = None


@dataclass(frozen=True)
class RunManifest:
    schema_version: str
    project_version: str
    experiment_id: str
    run_id: str
    status: RunStatus
    started_at: str
    completed_at: str | None
    git_commit: str
    python_version: str
    dependency_versions: Mapping[str, str]
    framework: str
    provider: str
    model: str
    model_call_date: str | None
    config_path: str
    config_hash: str
    dataset_name: str
    dataset_version: str
    dataset_hash: str
    seed: int
    repetition_id: int
    outputs: Mapping[str, str] = field(default_factory=dict)
    output_hashes: Mapping[str, str] = field(default_factory=dict)
    token_usage: ProviderUsage = field(default_factory=ProviderUsage)
    failure_reason: str | None = None
