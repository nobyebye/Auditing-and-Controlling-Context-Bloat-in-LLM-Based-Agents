"""Run independently validated natural-trace experiments."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import replace
from pathlib import Path

from context_auditor.adapters.common import DefaultIdGenerator, RegexTokenizer, UtcClock
from context_auditor.adapters.frameworks import LangChainRuntime
from context_auditor.adapters.providers import DeepSeekProvider, MockProvider
from context_auditor.adapters.providers.payload import (
    build_openai_payload,
    canonical_payload_bytes,
)
from context_auditor.adapters.storage import (
    FileDatasetRepository,
    JsonlTraceRepository,
    RunRegistry,
)
from context_auditor.adapters.storage.runs import require_clean_git_worktree
from context_auditor.application import BudgetedChatProvider, CaptureContext
from context_auditor.application.analysis import AnalyzeBloat
from context_auditor.application.call_budget import PersistentCallBudget
from context_auditor.application.reporting import BuildReport
from context_auditor.domain.models import (
    CaptureRequest,
    ModelRequestEnvelope,
    ProviderResponse,
    ProviderUsage,
    ScoringResult,
    ToolCall,
)
from context_auditor.ports import ChatProvider

from .external_config import ExternalValidationConfig
from .external_workflow import (
    NaturalInvocation,
    build_natural_request,
    build_tool_follow_up_request,
    execute_natural_workflow,
    score_tool_calls,
)
from .formal_runner import aggregate_usage, configure_log
from .protocol_lock import validate_protocol_registration


class RunExternalValidation:
    def __init__(
        self,
        project_root: str | Path,
        provider: ChatProvider | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.tokenizer = RegexTokenizer()
        self.datasets = FileDatasetRepository(self.project_root / "data")
        self.registry = RunRegistry(self.project_root / "runs")
        self.provider_override = provider

    def execute(
        self,
        config: ExternalValidationConfig,
        run_id: str | None = None,
    ) -> Path:
        protocol = None
        if config.provider != "mock":
            require_clean_git_worktree(self.project_root)
            protocol = validate_protocol_registration(
                self.project_root,
                phase=config.dataset_split,
            )
        base_provider = self.provider_override or build_external_provider(config)
        if (
            base_provider.provider_name != config.provider
            or base_provider.model != config.model
        ):
            raise ValueError("Provider identity does not match external config")
        budget = PersistentCallBudget(
            self.project_root / config.call_ledger_path,
            config.call_budget,
        )
        provider = BudgetedChatProvider(base_provider, budget)
        data = self.datasets.load(config.dataset_name, config.dataset_version)
        selected = [
            task
            for task in data["tasks"]
            if task.get("split") == config.dataset_split
        ]
        if config.task_ids:
            allowed = set(config.task_ids)
            selected = [task for task in selected if task["task_id"] in allowed]
            missing = sorted(allowed - {task["task_id"] for task in selected})
            if missing:
                raise ValueError("Missing configured task IDs: " + ", ".join(missing))
        if not selected:
            raise ValueError("External validation selected no tasks")
        validate_external_task_counts(selected, config.dataset_split)
        maximum_calls = sum(
            (
                config.max_provider_invocations_per_tool_cell
                if task["workflow_family"] == "multi_step_tool"
                else 1
            )
            for task in selected
        )
        if budget.remaining < maximum_calls:
            raise RuntimeError(
                f"External run needs at most {maximum_calls} calls but only "
                f"{budget.remaining} remain"
            )
        dataset_hash = self.datasets.content_hash(
            config.dataset_name,
            config.dataset_version,
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
            )
            if manifest.status.value == "completed":
                return paths.root
        else:
            paths, manifest = self.registry.create(
                experiment_id=config.experiment_id,
                framework=config.framework,
                provider=config.provider,
                model=config.model,
                config_path=self._portable_path(config.source_path),
                config_hash=config.config_hash,
                dataset_name=config.dataset_name,
                dataset_version=config.dataset_version,
                dataset_hash=dataset_hash,
                seed=config.randomization_seed,
                repetition_id=0,
                run_id=run_id,
                protocol_hash=(
                    protocol["manifest_sha256"] if protocol else None
                ),
            )
        logger, handler = configure_log(paths.log, manifest.run_id)
        try:
            traces = self._run(
                config,
                selected,
                provider,
                paths.traces,
                manifest.run_id,
                logger,
                budget,
            )
            summary = AnalyzeBloat().execute(traces)
            rules = json.loads(
                (
                    self.project_root
                    / "configs"
                    / "conclusions"
                    / "rq_rules_v2.json"
                ).read_text(encoding="utf-8")
            )
            BuildReport().execute(
                traces,
                summary,
                invocation_csv=paths.invocation_metrics,
                task_csv=paths.task_metrics,
                summary_json=paths.summary,
                rq_evidence_json=paths.rq_evidence,
                rq_rules=rules,
                tables_dir=paths.tables,
                figures_dir=paths.figures,
            )
            logger.info(
                "external_validation_completed traces=%d calls_used=%d",
                len(traces),
                budget.used,
            )
            handler.flush()
            self.registry.complete(paths, manifest, aggregate_usage(traces))
            return paths.root
        except Exception as error:
            logger.exception("external_validation_failed")
            handler.flush()
            self.registry.fail(paths, manifest, f"{type(error).__name__}: {error}")
            raise
        finally:
            logger.removeHandler(handler)
            handler.close()

    def _run(
        self,
        config: ExternalValidationConfig,
        tasks: list[dict],
        provider: ChatProvider,
        trace_path: Path,
        run_id: str,
        logger: logging.Logger,
        budget: PersistentCallBudget,
    ) -> list:
        repository = JsonlTraceRepository(trace_path)
        capture = CaptureContext(
            repository,
            self.tokenizer,
            UtcClock(),
            DefaultIdGenerator(),
        )
        langchain = (
            LangChainRuntime(provider) if config.framework == "langchain" else None
        )
        traces = list(repository.iter_traces())
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
            for trace in traces
            if trace.request_envelope
        }
        expected_cell_ids = {
            f"{task['task_id']}__{config.framework}" for task in tasks
        }
        orphaned = {
            key
            for key in budget.attempted_keys() - trace_dispatch_keys
            if key[0] in expected_cell_ids
        }
        if orphaned:
            raise RuntimeError(
                "Resume found provider attempts without immutable traces; "
                "requests will not be resent: "
                + repr(sorted(orphaned)[:10])
            )

        def invoke(envelope: ModelRequestEnvelope) -> ProviderResponse:
            try:
                if langchain:
                    response, _ = langchain.invoke(envelope)
                    return response
                return provider.invoke(envelope)
            except Exception as error:
                logger.error(
                    "provider_invocation_failed task_id=%s invocation=%s error=%s",
                    envelope.metadata.get("task_id", "unspecified"),
                    envelope.metadata.get("provider_invocation_index", 0),
                    type(error).__name__,
                )
                status = getattr(error, "code", None)
                return ProviderResponse(
                    content="",
                    usage=ProviderUsage(),
                    dispatch_error_type=type(error).__name__,
                    http_status=(
                        int(status) if isinstance(status, int) else None
                    ),
                )

        final_task_ids = {
            trace.task_id for trace in traces if trace.task_success is not None
        }
        for task in tasks:
            if task["task_id"] in final_task_ids:
                logger.info("resume_skip_completed task_id=%s", task["task_id"])
                continue

            def capture_invocation(invocation: NaturalInvocation) -> None:
                invocation_index = int(
                    invocation.request.metadata.get(
                        "provider_invocation_index",
                        0,
                    )
                )
                framework_hash = request_payload_hash(
                    invocation.request,
                    config.model,
                )
                trace = capture.execute(
                    CaptureRequest(
                        experiment_id=config.experiment_id,
                        run_id=run_id,
                        task_id=task["task_id"],
                        framework=config.framework,
                        provider=config.provider,
                        model=config.model,
                        configuration="natural_unmodified",
                        workflow_family=task["workflow_family"],
                        dataset_name=config.dataset_name,
                        dataset_version=config.dataset_version,
                        repetition_id=0,
                        seed=config.randomization_seed,
                        invocation_index=invocation_index,
                        messages=invocation.request.messages,
                        config_hash=config.config_hash,
                        request_envelope=invocation.request,
                        provider_request=invocation.response.request_record,
                        framework_capture_hash=framework_hash,
                        evidence_tier="natural",
                        intervention={
                            "final_invocation": invocation.final,
                            "dispatch_error_type": (
                                invocation.response.dispatch_error_type
                            ),
                            "http_status": invocation.response.http_status,
                            "provider_tool_calls": [
                                {
                                    "call_id": call.call_id,
                                    "name": call.name,
                                    "arguments": dict(call.arguments),
                                }
                                for call in invocation.response.tool_calls
                            ],
                        },
                        dataset_split=task["split"],
                        analysis_cohort="external_validation",
                        task_success=(
                            invocation.scoring.success
                            if invocation.final and invocation.scoring
                            else None
                        ),
                        task_output=invocation.response.content,
                        expected_answer=task.get("expected_answer"),
                        provider_usage=invocation.response.usage,
                        latency_ms=invocation.response.latency_ms,
                        generation_parameters=config.generation,
                        scoring=(
                            invocation.scoring if invocation.final else None
                        ),
                        privacy_mode=config.privacy_mode,
                    )
                )
                traces.append(trace)

            partial = [
                trace
                for trace in traces
                if trace.task_id == task["task_id"]
                and trace.task_success is None
                and trace.invocation_index == 0
            ]
            if partial:
                self._resume_tool_cell(
                    task,
                    config,
                    partial[-1],
                    invoke,
                    capture_invocation,
                )
                continue
            execute_natural_workflow(
                task,
                framework=config.framework,
                retrieval_top_k=config.retrieval_top_k,
                memory_top_k=config.memory_top_k,
                generation=config.generation,
                max_provider_invocations_per_tool_cell=(
                    config.max_provider_invocations_per_tool_cell
                ),
                randomization_seed=config.randomization_seed,
                invoke=invoke,
                on_invocation=capture_invocation,
            )
        return traces

    def _resume_tool_cell(
        self,
        task: dict,
        config: ExternalValidationConfig,
        partial,
        invoke,
        capture_invocation,
    ) -> None:
        if task["workflow_family"] != "multi_step_tool":
            raise RuntimeError(
                "Only a tool cell may contain a partial natural workflow"
            )
        raw_calls = partial.intervention.get("provider_tool_calls", [])
        tool_calls = tuple(
            ToolCall(
                call_id=str(item.get("call_id", "")),
                name=str(item.get("name", "")),
                arguments=item.get("arguments", {}),
            )
            for item in raw_calls
        )
        if not partial.request_envelope or not tool_calls:
            raise RuntimeError(
                "Partial tool trace lacks the frozen request or tool calls"
            )
        follow_up = build_tool_follow_up_request(
            partial.request_envelope,
            task=task,
            framework=config.framework,
            tool_calls=tool_calls,
            assistant_content=partial.task_output or "",
        )
        response = invoke(follow_up)
        first_response = ProviderResponse(content="", tool_calls=tool_calls)
        scoring = score_tool_calls(task, first_response)
        if response.dispatch_error_type:
            scoring = replace(
                scoring,
                success=False,
                score=0.0,
                details={
                    **scoring.details,
                    "termination_reason": "provider_dispatch_failed",
                    "error_type": response.dispatch_error_type,
                },
            )
        elif response.tool_calls:
            scoring = replace(
                scoring,
                success=False,
                score=0.0,
                details={
                    **scoring.details,
                    "termination_reason": (
                        "provider_invocation_cap_reached_before_third_dispatch"
                    ),
                },
            )
        capture_invocation(
            NaturalInvocation(follow_up, response, True, scoring)
        )

    def _portable_path(self, path: Path) -> Path:
        try:
            return path.resolve().relative_to(self.project_root.resolve())
        except ValueError:
            return path.resolve()


def build_external_provider(config: ExternalValidationConfig) -> ChatProvider:
    if config.provider == "mock":
        return MockProvider(config.model)
    if config.provider == "deepseek":
        return DeepSeekProvider.from_environment(config.model, config.generation)
    raise ValueError(f"Unsupported external provider: {config.provider}")


def request_payload_hash(request: ModelRequestEnvelope, model: str) -> str:
    return hashlib.sha256(
        canonical_payload_bytes(build_openai_payload(request, model))
    ).hexdigest()


def validate_external_task_counts(tasks: list[dict], split: str) -> None:
    expected = 4 if split == "calibration" else 20
    workflows = ("retrieval_qa", "memory_turns", "multi_step_tool")
    observed = {
        workflow: sum(
            task["workflow_family"] == workflow for task in tasks
        )
        for workflow in workflows
    }
    if observed != {workflow: expected for workflow in workflows}:
        raise ValueError(
            f"Frozen {split} design requires {expected} tasks per workflow; "
            f"observed {observed}"
        )
