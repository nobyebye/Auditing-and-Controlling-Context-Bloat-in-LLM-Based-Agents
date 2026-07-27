"""Counterfactual necessity and single-request mitigation replay study."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import random
from pathlib import Path

from context_auditor.adapters.common import DefaultIdGenerator, RegexTokenizer, UtcClock
from context_auditor.adapters.providers import (
    DeepSeekProvider,
    DeterministicCompressionBackend,
    LLMLingua2Compressor,
    MockProvider,
)
from context_auditor.adapters.providers.llmlingua2 import DEFAULT_MODEL_REVISION
from context_auditor.adapters.providers.payload import (
    build_openai_payload,
    canonical_payload_bytes,
)
from context_auditor.adapters.storage import JsonlTraceRepository, RunRegistry
from context_auditor.adapters.storage.runs import file_hash, require_clean_git_worktree
from context_auditor.application import (
    ApplyMitigation,
    BudgetedChatProvider,
    CaptureContext,
    build_counterfactual_variant,
)
from context_auditor.application.call_budget import PersistentCallBudget
from context_auditor.application.external_annotations import (
    annotation_eligible_segment,
    attach_adjudicated_annotations,
    load_bundle,
)
from context_auditor.domain.enums import PrivacyMode
from context_auditor.domain.models import (
    AuditTrace,
    CaptureRequest,
    GenerationParameters,
    ModelRequestEnvelope,
    ProviderResponse,
    ProviderUsage,
    ScoringResult,
    SCHEMA_VERSION,
)
from context_auditor.domain.text import hash_text
from context_auditor.experiments.formal_runner import aggregate_usage, configure_log
from context_auditor.experiments.protocol_lock import validate_protocol_registration
from context_auditor.experiments.scoring import score_response
from context_auditor.ports import ChatProvider


@dataclass(frozen=True)
class StudyCConfig:
    schema_version: str
    experiment_id: str
    provider: str
    model: str
    randomization_seed: int
    replicate_ids: tuple[str, str]
    call_budget: int
    call_ledger_path: str
    counterfactual_per_workflow_framework: int
    mitigation_task_ids: dict[str, tuple[str, ...]]
    generation: GenerationParameters
    privacy_mode: PrivacyMode
    llmlingua_model: str
    llmlingua_model_revision: str
    source_path: Path
    config_hash: str


@dataclass(frozen=True)
class PreparedMitigation:
    source_trace: AuditTrace
    arms: tuple[tuple[str, ModelRequestEnvelope, dict], ...]


def load_study_c_config(path: str | Path) -> StudyCConfig:
    source = Path(path)
    raw = source.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Study C config must use schema {SCHEMA_VERSION}")
    replicate_ids = tuple(str(item) for item in data.get("replicate_ids", []))
    if len(replicate_ids) != 2 or len(set(replicate_ids)) != 2:
        raise ValueError("Study C requires exactly two distinct replicate_ids")
    generation = GenerationParameters(**data.get("generation", {}))
    if generation.max_retries != 0:
        raise ValueError("Study C requires max_retries=0")
    if generation.thinking != "disabled":
        raise ValueError("Study C requires thinking=disabled")
    task_ids = {
        str(workflow): tuple(str(item) for item in values)
        for workflow, values in data.get("mitigation_task_ids", {}).items()
    }
    required_workflows = {
        "retrieval_qa",
        "memory_turns",
        "multi_step_tool",
    }
    if set(task_ids) != required_workflows:
        raise ValueError("Study C must freeze mitigation IDs for all workflows")
    if any(len(values) != 10 or len(set(values)) != 10 for values in task_ids.values()):
        raise ValueError("Study C requires 10 unique mitigation tasks per workflow")
    return StudyCConfig(
        schema_version=SCHEMA_VERSION,
        experiment_id=str(data["experiment_id"]),
        provider=str(data["provider"]),
        model=str(data["model"]),
        randomization_seed=int(data.get("randomization_seed", 20260727)),
        replicate_ids=(replicate_ids[0], replicate_ids[1]),
        call_budget=int(data.get("call_budget", 500)),
        call_ledger_path=str(data["call_ledger_path"]),
        counterfactual_per_workflow_framework=int(
            data.get("counterfactual_per_workflow_framework", 3)
        ),
        mitigation_task_ids=task_ids,
        generation=generation,
        privacy_mode=PrivacyMode(data.get("privacy_mode", "redacted")),
        llmlingua_model=str(data["llmlingua_model"]),
        llmlingua_model_revision=str(
            data.get("llmlingua_model_revision", DEFAULT_MODEL_REVISION)
        ),
        source_path=source,
        config_hash=hashlib.sha256(raw).hexdigest(),
    )


class RunStudyC:
    def __init__(
        self,
        project_root: str | Path,
        provider: ChatProvider | None = None,
        compressor: LLMLingua2Compressor | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.provider_override = provider
        self.compressor_override = compressor
        self.trace_tokenizer = RegexTokenizer()
        self.registry = RunRegistry(self.project_root / "runs")

    def execute(
        self,
        config: StudyCConfig,
        *,
        bundle_path: str | Path,
        adjudication_path: str | Path,
        answer_key_path: str | Path,
        annotation_set_id: str,
        run_id: str | None = None,
    ) -> Path:
        protocol = None
        if config.provider != "mock":
            require_clean_git_worktree(self.project_root)
            protocol = validate_protocol_registration(
                self.project_root,
                phase="test",
            )
        base_provider = self.provider_override or build_provider(config)
        if (
            base_provider.provider_name != config.provider
            or base_provider.model != config.model
        ):
            raise ValueError("Provider identity does not match Study C config")
        budget = PersistentCallBudget(
            self.project_root / config.call_ledger_path,
            config.call_budget,
        )
        provider = BudgetedChatProvider(base_provider, budget)
        compressor = self.compressor_override or LLMLingua2Compressor(
            config.llmlingua_model,
            model_revision=config.llmlingua_model_revision,
            backend=(
                DeterministicCompressionBackend()
                if config.provider == "mock"
                else None
            ),
            device="cpu",
        )
        traces, source_manifest = load_bundle(Path(bundle_path))
        annotated = attach_adjudicated_annotations(
            traces,
            adjudication_path,
            answer_key_path,
            annotation_set_id=annotation_set_id,
        )
        eligible = [
            trace
            for trace in annotated
            if trace.evidence_tier == "natural"
            and trace.task_success is not None
            and trace.dataset_split == "test"
        ]
        validate_annotation_completeness(eligible)
        counterfactual = select_counterfactual_contexts(
            eligible,
            per_group=config.counterfactual_per_workflow_framework,
            seed=config.randomization_seed,
        )
        mitigation = select_mitigation_contexts(
            eligible,
            task_ids=config.mitigation_task_ids,
        )
        prepared_mitigation = prepare_mitigation_cells(
            mitigation,
            config,
            compressor,
        )
        counterfactual_calls = (
            len(counterfactual) * 3 * len(config.replicate_ids)
        )
        mitigation_calls = len(prepared_mitigation) * 3
        if mitigation_calls != 180:
            raise ValueError(
                f"Frozen Study C mitigation design requires 180 calls, "
                f"observed {mitigation_calls}"
            )
        expected_calls = counterfactual_calls + mitigation_calls
        if expected_calls > 288:
            raise ValueError(f"Study C may issue at most 288 calls, observed {expected_calls}")
        if budget.remaining < expected_calls:
            raise RuntimeError(
                f"Study C needs {expected_calls} calls but only "
                f"{budget.remaining} remain"
            )
        source_bundle_hash = file_hash(Path(bundle_path))
        annotation_hash = hash_text(
            file_hash(Path(adjudication_path))
            + file_hash(Path(answer_key_path))
            + annotation_set_id
        )
        dataset_hash = source_manifest.get(
            "dataset_hash",
            hash_text(source_manifest["study_id"]),
        )
        existing_root = (
            self.project_root
            / "runs"
            / config.experiment_id
            / run_id
            if run_id
            else None
        )
        if existing_root and existing_root.exists():
            paths, manifest = self.registry.resume(
                experiment_id=config.experiment_id,
                run_id=run_id,
                config_hash=config.config_hash,
                dataset_hash=dataset_hash,
                protocol_hash=(
                    protocol["manifest_sha256"] if protocol else None
                ),
                source_bundle_hash=source_bundle_hash,
                annotation_hash=annotation_hash,
            )
            if manifest.status.value == "completed":
                return paths.root
        else:
            paths, manifest = self.registry.create(
                experiment_id=config.experiment_id,
                framework="multi-framework-replay",
                provider=config.provider,
                model=config.model,
                config_path=self._portable_path(config.source_path),
                config_hash=config.config_hash,
                dataset_name="external_validation",
                dataset_version="v1",
                dataset_hash=dataset_hash,
                seed=config.randomization_seed,
                repetition_id=0,
                run_id=run_id,
                protocol_hash=(
                    protocol["manifest_sha256"] if protocol else None
                ),
                source_bundle_hash=source_bundle_hash,
                annotation_hash=annotation_hash,
            )
        logger, handler = configure_log(paths.log, manifest.run_id)
        try:
            repository = JsonlTraceRepository(paths.traces)
            capture = CaptureContext(
                repository,
                self.trace_tokenizer,
                UtcClock(),
                DefaultIdGenerator(),
            )
            existing = list(repository.iter_traces())
            trace_dispatch_keys = {
                (
                    str(trace.request_envelope.metadata.get("cell_id")),
                    str(trace.request_envelope.metadata.get("arm")),
                    int(
                        trace.request_envelope.metadata.get(
                            "provider_invocation_index",
                            0,
                        )
                    ),
                )
                for trace in existing
                if trace.request_envelope
            }
            parent_ids = {
                trace.trace_id for trace in mitigation
            } | {
                trace.trace_id for trace, _remove, _keep in counterfactual
            }
            orphaned = {
                key
                for key in budget.attempted_keys() - trace_dispatch_keys
                if any(key[0].startswith(parent + "__") for parent in parent_ids)
            }
            if orphaned:
                raise RuntimeError(
                    "Resume found Study C provider attempts without immutable "
                    "traces; requests will not be resent: "
                    + repr(sorted(orphaned)[:10])
                )
            completed_cells = {
                replay_cell_key(trace)
                for trace in existing
            }
            self._run_counterfactual(
                config,
                counterfactual,
                provider,
                capture,
                manifest.run_id,
                completed_cells,
                logger,
            )
            self._run_mitigation(
                config,
                prepared_mitigation,
                provider,
                capture,
                manifest.run_id,
                completed_cells,
                logger,
            )
            results = list(repository.iter_traces())
            summary = {
                "schema_version": SCHEMA_VERSION,
                "study": "C",
                "trace_count": len(results),
                "counterfactual_context_count": len(counterfactual),
                "counterfactual_trace_count": sum(
                    trace.evidence_tier == "counterfactual"
                    for trace in results
                ),
                "mitigation_trace_count": sum(
                    trace.evidence_tier == "mitigation"
                    for trace in results
                ),
                "independent_task_count": len({trace.task_id for trace in results}),
                "calls_used_total": budget.used,
                "calls_remaining": budget.remaining,
                "maximum_planned_provider_calls": expected_calls,
                "annotation_set_id": annotation_set_id,
                "source_bundle_sha256": source_bundle_hash,
                "adjudication_sha256": file_hash(Path(adjudication_path)),
                "answer_key_sha256": file_hash(Path(answer_key_path)),
                "source_study_id": source_manifest["study_id"],
                "llmlingua_model": config.llmlingua_model,
                "llmlingua_model_revision": config.llmlingua_model_revision,
                "budget_preflight_passed": True,
                "mitigation_provider_requests_per_arm": 1,
            }
            paths.summary.write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            logger.info("study_c_completed traces=%d", len(results))
            handler.flush()
            self.registry.complete(paths, manifest, aggregate_usage(results))
            return paths.root
        except Exception as error:
            logger.exception("study_c_failed")
            handler.flush()
            self.registry.fail(paths, manifest, f"{type(error).__name__}: {error}")
            raise
        finally:
            logger.removeHandler(handler)
            handler.close()

    def _run_counterfactual(
        self,
        config: StudyCConfig,
        selections: list[tuple[AuditTrace, str, str]],
        provider: ChatProvider,
        capture: CaptureContext,
        run_id: str,
        completed_cells: set[tuple],
        logger,
    ) -> None:
        for source_trace, remove_id, keep_id in selections:
            variants = (
                ("counterfactual_baseline", source_trace.request_envelope, ()),
                (
                    "remove_human_candidate",
                    build_counterfactual_variant(
                        source_trace,
                        (remove_id,),
                        variant_type="remove_human_candidate",
                    ).request,
                    (remove_id,),
                ),
                (
                    "remove_matched_keep",
                    build_counterfactual_variant(
                        source_trace,
                        (keep_id,),
                        variant_type="remove_matched_keep",
                    ).request,
                    (keep_id,),
                ),
            )
            for repetition_id, replicate_id in enumerate(config.replicate_ids):
                for name, request, removed_ids in variants:
                    key = (
                        source_trace.trace_id,
                        name,
                        replicate_id,
                    )
                    if key in completed_cells:
                        logger.info("resume_skip_completed cell=%s", key)
                        continue
                    prepared = prepare_replay_request(
                        request,
                        config=config,
                        source_trace=source_trace,
                        arm=name,
                        replicate_id=replicate_id,
                    )
                    response = invoke_itt(provider, prepared)
                    scoring = score_replay(source_trace, response)
                    trace = capture_replay(
                        capture,
                        config,
                        source_trace,
                        request=prepared,
                        response=response,
                        run_id=run_id,
                        configuration=name,
                        repetition_id=repetition_id,
                        evidence_tier="counterfactual",
                        scoring=scoring,
                        intervention={
                            "type": name,
                            "removed_segment_ids": list(removed_ids),
                            "matched_pair": True,
                            "conditional_candidate": True,
                        },
                    )
                    completed_cells.add(replay_cell_key(trace))

    def _run_mitigation(
        self,
        config: StudyCConfig,
        cells: list[PreparedMitigation],
        provider: ChatProvider,
        capture: CaptureContext,
        run_id: str,
        completed_cells: set[tuple],
        logger,
    ) -> None:
        for cell in cells:
            for name, request, intervention in cell.arms:
                key = (cell.source_trace.trace_id, name, "single")
                if key in completed_cells:
                    logger.info("resume_skip_completed cell=%s", key)
                    continue
                response = invoke_itt(provider, request)
                scoring = score_replay(cell.source_trace, response)
                trace = capture_replay(
                    capture,
                    config,
                    cell.source_trace,
                    request=request,
                    response=response,
                    run_id=run_id,
                    configuration=name,
                    repetition_id=0,
                    evidence_tier="mitigation",
                    scoring=scoring,
                    intervention=intervention,
                )
                completed_cells.add(replay_cell_key(trace))

    def _portable_path(self, path: Path) -> Path:
        try:
            return path.resolve().relative_to(self.project_root.resolve())
        except ValueError:
            return path.resolve()


def prepare_mitigation_cells(
    traces: list[AuditTrace],
    config: StudyCConfig,
    compressor: LLMLingua2Compressor,
) -> list[PreparedMitigation]:
    mitigation = ApplyMitigation(RegexTokenizer())
    prepared: list[PreparedMitigation] = []
    failures = []
    for source_trace in traces:
        if not source_trace.request_envelope:
            raise ValueError("Mitigation replay requires a request envelope")
        query = last_user_message(source_trace.request_envelope.messages)
        provenance = mitigation.execute(
            source_trace.request_envelope.messages,
            query,
            "source-aware",
        )
        target = compressor.count_managed(provenance.messages)
        compressed = compressor.compress(
            source_trace.request_envelope.messages,
            target_tokens=max(1, target),
        )
        if not compressed.within_tolerance:
            failures.append(
                {
                    "trace_id": source_trace.trace_id,
                    "target": target,
                    "actual": compressed.actual_managed_tokens,
                    "tolerance": compressed.tolerance_tokens,
                }
            )
            continue
        arms = (
            (
                "unmodified",
                source_trace.request_envelope,
                {"type": "none", "single_request_replay": True},
            ),
            (
                "provenance_aware",
                replace(
                    source_trace.request_envelope,
                    messages=provenance.messages,
                ),
                {
                    "type": "provenance_aware",
                    "target_managed_tokens": target,
                    "actual_managed_tokens": target,
                    "decision_count": len(provenance.decisions),
                    "single_request_replay": True,
                },
            ),
            (
                "llmlingua2_budget_matched",
                replace(
                    source_trace.request_envelope,
                    messages=compressed.messages,
                ),
                {
                    "type": "llmlingua2",
                    "target_managed_tokens": target,
                    "actual_managed_tokens": compressed.actual_managed_tokens,
                    "tolerance_tokens": compressed.tolerance_tokens,
                    "model": config.llmlingua_model,
                    "model_revision": config.llmlingua_model_revision,
                    "single_request_replay": True,
                },
            ),
        )
        prepared.append(
            PreparedMitigation(
                source_trace=source_trace,
                arms=tuple(
                    (
                        name,
                        prepare_replay_request(
                            request,
                            config=config,
                            source_trace=source_trace,
                            arm=name,
                            replicate_id="single",
                        ),
                        intervention,
                    )
                    for name, request, intervention in arms
                ),
            )
        )
    if failures:
        raise RuntimeError(
            "LLMLingua budget preflight failed: "
            + json.dumps(failures[:10], sort_keys=True)
        )
    return prepared


def prepare_replay_request(
    request: ModelRequestEnvelope | None,
    *,
    config: StudyCConfig,
    source_trace: AuditTrace,
    arm: str,
    replicate_id: str,
) -> ModelRequestEnvelope:
    if request is None:
        raise ValueError("Study C replay requires a frozen request envelope")
    generation = replace(
        config.generation,
        max_retries=0,
        thinking="disabled",
        tool_choice="none",
    )
    cell_id = f"{source_trace.trace_id}__{arm}__{replicate_id}"
    return replace(
        request,
        generation_parameters=generation,
        randomization_seed=config.randomization_seed,
        replicate_id=replicate_id,
        provider_seed=None,
        metadata={
            **request.metadata,
            "cell_id": cell_id,
            "task_id": source_trace.task_id,
            "framework": source_trace.framework,
            "arm": arm,
            "provider_invocation_index": 0,
            "single_request_replay": True,
        },
    )


def invoke_itt(
    provider: ChatProvider,
    request: ModelRequestEnvelope,
) -> ProviderResponse:
    try:
        return provider.invoke(request)
    except Exception as error:
        status = getattr(error, "code", None)
        return ProviderResponse(
            content="",
            usage=ProviderUsage(),
            dispatch_error_type=type(error).__name__,
            http_status=int(status) if isinstance(status, int) else None,
        )


def select_counterfactual_contexts(
    traces: list[AuditTrace],
    *,
    per_group: int,
    seed: int,
) -> list[tuple[AuditTrace, str, str]]:
    protected = {"system", "user", "framework", "tool_schema"}
    groups: dict[
        tuple[str, str],
        list[tuple[AuditTrace, list[tuple[str, str]]]],
    ] = {}
    for trace in traces:
        annotations = {
            item.segment_id: item
            for item in trace.reference_annotations
            if item.adjudicated
        }
        pairs = []
        for segment in trace.segments:
            annotation = annotations.get(segment.segment_id)
            if (
                not annotation
                or annotation.decision != "remove"
                or not segment.text.strip()
                or segment.source_type in protected
            ):
                continue
            controls = [
                other
                for other in trace.segments
                if other.source_type == segment.source_type
                and other.segment_id in annotations
                and annotations[other.segment_id].decision == "keep"
                and other.text.strip()
            ]
            if not controls:
                continue
            control = min(
                controls,
                key=lambda item: (
                    abs(item.token_count - segment.token_count),
                    item.content_hash,
                    item.segment_id,
                ),
            )
            pairs.append((segment.segment_id, control.segment_id))
        if pairs:
            groups.setdefault(
                (trace.workflow_family, trace.framework),
                [],
            ).append((trace, pairs))
    generator = random.Random(seed)
    selected = []
    for key in sorted(groups):
        contexts = sorted(
            groups[key],
            key=lambda item: (item[0].task_id, item[0].trace_id),
        )
        chosen = generator.sample(contexts, min(per_group, len(contexts)))
        for trace, pairs in chosen:
            remove_id, keep_id = generator.choice(sorted(pairs))
            selected.append((trace, remove_id, keep_id))
    return selected


def select_mitigation_contexts(
    traces: list[AuditTrace],
    *,
    task_ids: dict[str, tuple[str, ...]],
) -> list[AuditTrace]:
    by_key = {
        (trace.workflow_family, trace.task_id, trace.framework): trace
        for trace in traces
    }
    selected = []
    missing = []
    for workflow, ids in sorted(task_ids.items()):
        for task_id in ids:
            for framework in ("custom-react", "langchain"):
                trace = by_key.get((workflow, task_id, framework))
                if trace is None:
                    missing.append((workflow, task_id, framework))
                else:
                    selected.append(trace)
    if missing:
        raise ValueError(f"Frozen mitigation cells are missing: {missing[:10]}")
    return selected


def capture_replay(
    capture: CaptureContext,
    config: StudyCConfig,
    source_trace: AuditTrace,
    *,
    request: ModelRequestEnvelope,
    response: ProviderResponse,
    run_id: str,
    configuration: str,
    repetition_id: int,
    evidence_tier: str,
    scoring: ScoringResult,
    intervention: dict,
) -> AuditTrace:
    capture_hash = hashlib.sha256(
        canonical_payload_bytes(build_openai_payload(request, source_trace.model))
    ).hexdigest()
    return capture.execute(
        CaptureRequest(
            experiment_id=config.experiment_id,
            run_id=run_id,
            task_id=source_trace.task_id,
            framework=source_trace.framework,
            provider=source_trace.provider,
            model=source_trace.model,
            configuration=configuration,
            workflow_family=source_trace.workflow_family,
            dataset_name=source_trace.dataset_name,
            dataset_version=source_trace.dataset_version,
            repetition_id=repetition_id,
            seed=config.randomization_seed,
            invocation_index=0,
            messages=request.messages,
            config_hash=config.config_hash,
            request_envelope=request,
            provider_request=response.request_record,
            framework_capture_hash=capture_hash,
            evidence_tier=evidence_tier,
            parent_trace_id=source_trace.trace_id,
            intervention={
                **intervention,
                "dispatch_error_type": response.dispatch_error_type,
                "http_status": response.http_status,
            },
            dataset_split=source_trace.dataset_split,
            analysis_cohort="external_validation",
            task_success=scoring.success,
            task_output=response.content,
            expected_answer=source_trace.expected_answer,
            provider_usage=response.usage,
            latency_ms=response.latency_ms,
            generation_parameters=request.generation_parameters,
            scoring=scoring,
            privacy_mode=config.privacy_mode,
        )
    )


def score_replay(trace: AuditTrace, response: ProviderResponse) -> ScoringResult:
    if response.dispatch_error_type:
        return ScoringResult(
            success=False,
            score=0.0,
            method="provider_failure_intention_to_treat",
            normalized_output="",
            normalized_expected="",
            details={"error_type": response.dispatch_error_type},
        )
    if trace.workflow_family == "multi_step_tool":
        success = bool(response.content.strip())
        return ScoringResult(
            success=success,
            score=1.0 if success else 0.0,
            method="provider_completed_nonempty_tool_final_replay",
            normalized_output=response.content.strip(),
            normalized_expected="human_review_required",
        )
    method = trace.scoring.method if trace.scoring else "contains"
    if method not in {
        "contains",
        "exact",
        "token_f1",
        "hotpotqa_f1",
        "numeric",
    }:
        method = "contains"
    return score_response(
        {
            "expected_answer": trace.expected_answer or "",
            "scoring": {"type": method, "minimum_f1": 0.8},
        },
        response.content,
    )


def validate_annotation_completeness(traces: list[AuditTrace]) -> None:
    incomplete = [
        trace.trace_id
        for trace in traces
        if len(trace.reference_annotations)
        != sum(
            annotation_eligible_segment(segment)
            for segment in trace.segments
        )
    ]
    if incomplete:
        raise ValueError(
            "Study C requires complete adjudicated annotations: "
            + ", ".join(incomplete[:10])
        )


def replay_cell_key(trace: AuditTrace) -> tuple[str | None, str, str]:
    return (
        trace.parent_trace_id,
        trace.configuration,
        trace.replicate_id or "single",
    )


def last_user_message(messages: tuple) -> str:
    return next(
        (
            message.content
            for message in reversed(messages)
            if message.role == "user"
        ),
        "",
    )


def build_provider(config: StudyCConfig) -> ChatProvider:
    if config.provider == "mock":
        return MockProvider(config.model)
    if config.provider == "deepseek":
        return DeepSeekProvider.from_environment(config.model, config.generation)
    raise ValueError(f"Unsupported Study C provider: {config.provider}")
