"""Counterfactual necessity and budget-matched mitigation replay study."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, replace
from pathlib import Path

from context_auditor.adapters.common import DefaultIdGenerator, RegexTokenizer, UtcClock
from context_auditor.adapters.providers import (
    DeepSeekProvider,
    DeterministicCompressionBackend,
    LLMLingua2Compressor,
    MockProvider,
)
from context_auditor.adapters.providers.payload import (
    build_openai_payload,
    canonical_payload_bytes,
)
from context_auditor.adapters.storage import JsonlTraceRepository, RunRegistry
from context_auditor.adapters.storage.runs import (
    file_hash,
    require_clean_git_worktree,
)
from context_auditor.application import (
    ApplyMitigation,
    BudgetedChatProvider,
    CaptureContext,
    build_counterfactual_variant,
)
from context_auditor.application.call_budget import PersistentCallBudget
from context_auditor.application.external_annotations import (
    attach_adjudicated_annotations,
    load_bundle,
)
from context_auditor.domain.enums import PrivacyMode
from context_auditor.domain.models import (
    AuditTrace,
    CaptureRequest,
    GenerationParameters,
    Message,
    ModelRequestEnvelope,
    ScoringResult,
    SCHEMA_VERSION,
)
from context_auditor.domain.text import hash_text
from context_auditor.experiments.external_workflow import score_tool_calls
from context_auditor.experiments.formal_runner import aggregate_usage, configure_log
from context_auditor.experiments.scoring import score_response
from context_auditor.experiments.protocol_lock import validate_protocol_registration
from context_auditor.ports import ChatProvider


@dataclass(frozen=True)
class StudyCConfig:
    schema_version: str
    experiment_id: str
    provider: str
    model: str
    seed: int
    repetition_seeds: tuple[int, int]
    call_budget: int
    call_ledger_path: str
    counterfactual_per_workflow_framework: int
    mitigation_tasks_per_workflow: int
    generation: GenerationParameters
    privacy_mode: PrivacyMode
    llmlingua_model: str
    source_path: Path
    config_hash: str


def load_study_c_config(path: str | Path) -> StudyCConfig:
    source = Path(path)
    raw = source.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Study C config must use schema {SCHEMA_VERSION}")
    seeds = tuple(int(item) for item in data.get("repetition_seeds", []))
    if len(seeds) != 2:
        raise ValueError("Study C requires exactly two repetition seeds")
    return StudyCConfig(
        schema_version=SCHEMA_VERSION,
        experiment_id=str(data["experiment_id"]),
        provider=str(data["provider"]),
        model=str(data["model"]),
        seed=int(data.get("seed", 20260727)),
        repetition_seeds=(seeds[0], seeds[1]),
        call_budget=int(data.get("call_budget", 500)),
        call_ledger_path=str(data["call_ledger_path"]),
        counterfactual_per_workflow_framework=int(
            data.get("counterfactual_per_workflow_framework", 3)
        ),
        mitigation_tasks_per_workflow=int(
            data.get("mitigation_tasks_per_workflow", 10)
        ),
        generation=GenerationParameters(**data.get("generation", {})),
        privacy_mode=PrivacyMode(data.get("privacy_mode", "redacted")),
        llmlingua_model=str(
            data.get(
                "llmlingua_model",
                "microsoft/llmlingua-2-xlm-roberta-large-meetingbank",
            )
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
        self.tokenizer = RegexTokenizer()
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
        if config.provider != "mock":
            require_clean_git_worktree(self.project_root)
            validate_protocol_registration(self.project_root)
        base_provider = self.provider_override or build_provider(config)
        budget = PersistentCallBudget(
            self.project_root / config.call_ledger_path,
            config.call_budget,
        )
        provider = BudgetedChatProvider(base_provider, budget)
        compressor = self.compressor_override or LLMLingua2Compressor(
            config.llmlingua_model,
            backend=(
                DeterministicCompressionBackend()
                if config.provider == "mock"
                else None
            ),
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
            seed=config.seed,
        )
        mitigation = select_mitigation_contexts(
            eligible,
            tasks_per_workflow=config.mitigation_tasks_per_workflow,
            seed=config.seed,
        )
        expected_calls = (
            len(counterfactual) * 3 * len(config.repetition_seeds)
            + len(mitigation) * 3
        )
        if expected_calls != 288:
            raise ValueError(
                f"Frozen Study C design requires 288 calls, observed {expected_calls}"
            )
        if budget.remaining < expected_calls:
            raise RuntimeError(
                f"Study C needs {expected_calls} calls but only "
                f"{budget.remaining} remain"
            )
        paths, manifest = self.registry.create(
            experiment_id=config.experiment_id,
            framework="multi-framework-replay",
            provider=config.provider,
            model=config.model,
            config_path=self._portable_path(config.source_path),
            config_hash=config.config_hash,
            dataset_name="external_validation",
            dataset_version="v1",
            dataset_hash=source_manifest.get(
                "dataset_hash",
                hash_text(source_manifest["study_id"]),
            ),
            seed=config.seed,
            repetition_id=0,
            run_id=run_id,
        )
        logger, handler = configure_log(paths.log, manifest.run_id)
        try:
            repository = JsonlTraceRepository(paths.traces)
            capture = CaptureContext(
                repository,
                self.tokenizer,
                UtcClock(),
                DefaultIdGenerator(),
            )
            results = [
                *self._run_counterfactual(
                    config,
                    counterfactual,
                    provider,
                    capture,
                    manifest.run_id,
                ),
                *self._run_mitigation(
                    config,
                    mitigation,
                    provider,
                    compressor,
                    capture,
                    manifest.run_id,
                ),
            ]
            summary = {
                "schema_version": SCHEMA_VERSION,
                "study": "C",
                "trace_count": len(results),
                "counterfactual_trace_count": len(counterfactual)
                * 3
                * len(config.repetition_seeds),
                "mitigation_trace_count": len(mitigation) * 3,
                "independent_task_count": len(
                    {trace.task_id for trace in results}
                ),
                "calls_used_total": budget.used,
                "calls_remaining": budget.remaining,
                "expected_provider_calls": expected_calls,
                "annotation_set_id": annotation_set_id,
                "source_bundle_sha256": file_hash(Path(bundle_path)),
                "adjudication_sha256": file_hash(Path(adjudication_path)),
                "answer_key_sha256": file_hash(Path(answer_key_path)),
                "source_study_id": source_manifest["study_id"],
                "llmlingua_model": config.llmlingua_model,
                "counterfactual_parent_trace_ids": sorted(
                    {trace.trace_id for trace, _remove, _keep in counterfactual}
                ),
                "mitigation_parent_trace_ids": sorted(
                    trace.trace_id for trace in mitigation
                ),
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
    ) -> list[AuditTrace]:
        results = []
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
                    "remove_matched_necessary",
                    build_counterfactual_variant(
                        source_trace,
                        (keep_id,),
                        variant_type="remove_matched_necessary",
                    ).request,
                    (keep_id,),
                ),
            )
            for repetition_id, seed in enumerate(config.repetition_seeds):
                for name, request, removed_ids in variants:
                    seeded = replace(
                        request,
                        generation_parameters=config.generation,
                        metadata={**request.metadata, "study_seed": seed},
                    )
                    response = provider.invoke(seeded)
                    scoring = score_replay(source_trace, response)
                    results.append(
                        capture_replay(
                            capture,
                            source_trace,
                            request=seeded,
                            response=response,
                            run_id=run_id,
                            configuration=name,
                            repetition_id=repetition_id,
                            seed=seed,
                            evidence_tier="counterfactual",
                            scoring=scoring,
                            intervention={
                                "type": name,
                                "removed_segment_ids": list(removed_ids),
                                "matched_pair": True,
                            },
                            privacy_mode=config.privacy_mode,
                        )
                    )
        return results

    def _run_mitigation(
        self,
        config: StudyCConfig,
        traces: list[AuditTrace],
        provider: ChatProvider,
        compressor: LLMLingua2Compressor,
        capture: CaptureContext,
        run_id: str,
    ) -> list[AuditTrace]:
        mitigation = ApplyMitigation(self.tokenizer)
        results = []
        for source_trace in traces:
            if not source_trace.request_envelope:
                raise ValueError("Mitigation replay requires a request envelope")
            query = last_user_message(source_trace.request_envelope.messages)
            provenance = mitigation.execute(
                source_trace.request_envelope.messages,
                query,
                "source-aware",
            )
            retained_managed_tokens = managed_token_count(
                provenance.messages,
                self.tokenizer,
            )
            llmlingua_messages = compressor.compress(
                source_trace.request_envelope.messages,
                target_tokens=max(1, retained_managed_tokens),
            )
            arms = (
                (
                    "unmodified",
                    source_trace.request_envelope,
                    {"type": "none"},
                ),
                (
                    "provenance_aware",
                    replace(
                        source_trace.request_envelope,
                        messages=provenance.messages,
                    ),
                    {
                        "type": "provenance_aware",
                        "target_managed_tokens": retained_managed_tokens,
                        "decision_count": len(provenance.decisions),
                    },
                ),
                (
                    "llmlingua2_budget_matched",
                    replace(
                        source_trace.request_envelope,
                        messages=llmlingua_messages,
                    ),
                    {
                        "type": "llmlingua2",
                        "target_managed_tokens": retained_managed_tokens,
                        "model": config.llmlingua_model,
                    },
                ),
            )
            for name, request, intervention in arms:
                prepared = replace(
                    request,
                    generation_parameters=config.generation,
                    metadata={**request.metadata, "study_seed": config.seed},
                )
                response = provider.invoke(prepared)
                scoring = score_replay(source_trace, response)
                results.append(
                    capture_replay(
                        capture,
                        source_trace,
                        request=prepared,
                        response=response,
                        run_id=run_id,
                        configuration=name,
                        repetition_id=0,
                        seed=config.seed,
                        evidence_tier="mitigation",
                        scoring=scoring,
                        intervention=intervention,
                        privacy_mode=config.privacy_mode,
                    )
                )
        return results

    def _portable_path(self, path: Path) -> Path:
        try:
            return path.resolve().relative_to(self.project_root.resolve())
        except ValueError:
            return path.resolve()


def select_counterfactual_contexts(
    traces: list[AuditTrace],
    *,
    per_group: int,
    seed: int,
) -> list[tuple[AuditTrace, str, str]]:
    groups: dict[tuple[str, str], list[tuple[AuditTrace, str, str]]] = {}
    for trace in traces:
        remove = [
            item
            for item in trace.reference_annotations
            if item.decision == "remove"
            and segment_source(trace, item.segment_id)
            in {"retrieval", "memory", "tool"}
        ]
        keep = [
            item
            for item in trace.reference_annotations
            if item.decision == "keep"
            and segment_source(trace, item.segment_id)
            in {"retrieval", "memory", "tool", "generated_trace"}
        ]
        if not remove or not keep:
            continue
        candidate = max(remove, key=lambda item: segment_tokens(trace, item.segment_id))
        control = min(
            keep,
            key=lambda item: abs(
                segment_tokens(trace, item.segment_id)
                - segment_tokens(trace, candidate.segment_id)
            ),
        )
        groups.setdefault((trace.workflow_family, trace.framework), []).append(
            (trace, candidate.segment_id, control.segment_id)
        )
    expected_groups = {
        (workflow, framework)
        for workflow in ("retrieval_qa", "memory_turns", "multi_step_tool")
        for framework in ("langchain", "custom-react")
    }
    if set(groups) != expected_groups:
        missing = sorted(expected_groups - set(groups))
        raise ValueError(f"Counterfactual groups lack eligible traces: {missing}")
    generator = random.Random(seed)
    selected = []
    for key in sorted(groups):
        candidates = sorted(groups[key], key=lambda item: item[0].task_id)
        if len(candidates) < per_group:
            raise ValueError(f"Counterfactual group {key} has too few contexts")
        selected.extend(generator.sample(candidates, per_group))
    return selected


def select_mitigation_contexts(
    traces: list[AuditTrace],
    *,
    tasks_per_workflow: int,
    seed: int,
) -> list[AuditTrace]:
    by_workflow_task: dict[str, dict[str, list[AuditTrace]]] = {}
    for trace in traces:
        by_workflow_task.setdefault(trace.workflow_family, {}).setdefault(
            trace.task_id,
            [],
        ).append(trace)
    generator = random.Random(seed)
    selected = []
    for workflow in ("retrieval_qa", "memory_turns", "multi_step_tool"):
        tasks = by_workflow_task.get(workflow, {})
        eligible = [
            task_id
            for task_id, task_traces in tasks.items()
            if {trace.framework for trace in task_traces}
            == {"langchain", "custom-react"}
        ]
        if len(eligible) < tasks_per_workflow:
            raise ValueError(f"Mitigation workflow {workflow} has too few paired tasks")
        chosen = generator.sample(sorted(eligible), tasks_per_workflow)
        for task_id in chosen:
            selected.extend(
                sorted(tasks[task_id], key=lambda trace: trace.framework)
            )
    return selected


def capture_replay(
    capture: CaptureContext,
    source_trace: AuditTrace,
    *,
    request: ModelRequestEnvelope,
    response,
    run_id: str,
    configuration: str,
    repetition_id: int,
    seed: int,
    evidence_tier: str,
    scoring: ScoringResult,
    intervention: dict,
    privacy_mode: PrivacyMode,
) -> AuditTrace:
    capture_hash = hashlib.sha256(
        canonical_payload_bytes(build_openai_payload(request, source_trace.model))
    ).hexdigest()
    return capture.execute(
        CaptureRequest(
            experiment_id="external-validation-study-c-v1.2",
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
            seed=seed,
            invocation_index=0,
            messages=request.messages,
            config_hash=source_trace.config_hash,
            request_envelope=request,
            provider_request=response.request_record,
            framework_capture_hash=capture_hash,
            evidence_tier=evidence_tier,
            parent_trace_id=source_trace.trace_id,
            intervention=intervention,
            dataset_split=source_trace.dataset_split,
            analysis_cohort="external_validation",
            task_success=scoring.success,
            task_output=response.content,
            expected_answer=source_trace.expected_answer,
            provider_usage=response.usage,
            latency_ms=response.latency_ms,
            generation_parameters=request.generation_parameters,
            scoring=scoring,
            privacy_mode=privacy_mode,
        )
    )


def score_replay(trace: AuditTrace, response) -> ScoringResult:
    if trace.scoring and trace.scoring.method == "bfcl_tool_call_exact":
        expected = json.loads(trace.expected_answer or "[]")
        tools = (
            [
                {
                    "name": tool.name,
                    "parameters": dict(tool.parameters),
                }
                for tool in trace.request_envelope.tools
            ]
            if trace.request_envelope
            else []
        )
        return score_tool_calls(
            {"expected_tool_calls": expected, "tools": tools},
            response,
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
        if len(trace.reference_annotations) != len(trace.segments)
    ]
    if incomplete:
        raise ValueError(
            "Study C requires complete adjudicated annotations: "
            + ", ".join(incomplete[:10])
        )


def segment_source(trace: AuditTrace, segment_id: str) -> str:
    return next(
        segment.source_type
        for segment in trace.segments
        if segment.segment_id == segment_id
    )


def segment_tokens(trace: AuditTrace, segment_id: str) -> int:
    return next(
        segment.token_count
        for segment in trace.segments
        if segment.segment_id == segment_id
    )


def managed_token_count(messages: tuple[Message, ...], tokenizer) -> int:
    return sum(
        tokenizer.count(message.content)
        for message in messages
        if message.metadata.get("source_type") in {"retrieval", "memory", "tool"}
        or message.role == "tool"
    )


def last_user_message(messages: tuple[Message, ...]) -> str:
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
