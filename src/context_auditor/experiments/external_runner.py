"""Run independently validated natural-trace experiments."""

from __future__ import annotations

import hashlib
import json
import logging
import time
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
)
from context_auditor.ports import ChatProvider

from .external_config import ExternalValidationConfig
from .external_workflow import build_natural_request, execute_natural_workflow
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
        if config.provider != "mock":
            require_clean_git_worktree(self.project_root)
            validate_protocol_registration(self.project_root)
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
        paths, manifest = self.registry.create(
            experiment_id=config.experiment_id,
            framework=config.framework,
            provider=config.provider,
            model=config.model,
            config_path=self._portable_path(config.source_path),
            config_hash=config.config_hash,
            dataset_name=config.dataset_name,
            dataset_version=config.dataset_version,
            dataset_hash=self.datasets.content_hash(
                config.dataset_name,
                config.dataset_version,
            ),
            seed=config.seed,
            repetition_id=0,
            run_id=run_id,
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
        traces = []

        def invoke(envelope: ModelRequestEnvelope) -> ProviderResponse:
            for attempt in range(config.generation.max_retries + 1):
                try:
                    if langchain:
                        response, _ = langchain.invoke(envelope)
                        return response
                    return provider.invoke(envelope)
                except Exception:
                    if attempt >= config.generation.max_retries:
                        raise
                    delay = min(8.0, 2.0**attempt)
                    logger.warning(
                        "provider_retry attempt=%d delay=%.1f",
                        attempt + 1,
                        delay,
                    )
                    time.sleep(delay)
            raise RuntimeError("Provider retry loop exited unexpectedly")

        for task in tasks:
            try:
                invocations = execute_natural_workflow(
                    task,
                    framework=config.framework,
                    retrieval_top_k=config.retrieval_top_k,
                    memory_top_k=config.memory_top_k,
                    generation=config.generation,
                    max_tool_invocations=config.max_tool_invocations,
                    invoke=invoke,
                )
            except Exception as error:
                logger.error(
                    "task_failed task_id=%s error=%s",
                    task["task_id"],
                    type(error).__name__,
                )
                request = build_natural_request(
                    task,
                    framework=config.framework,
                    retrieval_top_k=config.retrieval_top_k,
                    memory_top_k=config.memory_top_k,
                    generation=config.generation,
                )
                invocations = (
                    failed_invocation(request, type(error).__name__),
                )
            for invocation_index, invocation in enumerate(invocations):
                framework_hash = request_payload_hash(
                    invocation.request,
                    config.model,
                )
                traces.append(
                    capture.execute(
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
                            seed=config.seed,
                            invocation_index=invocation_index,
                            messages=invocation.request.messages,
                            config_hash=config.config_hash,
                            request_envelope=invocation.request,
                            provider_request=invocation.response.request_record,
                            framework_capture_hash=framework_hash,
                            evidence_tier="natural",
                            dataset_split=task["split"],
                            analysis_cohort="external_validation",
                            task_success=(
                                invocation.scoring.success
                                if invocation.final and invocation.scoring
                                else None
                            ),
                            task_output=(
                                invocation.response.content
                                if invocation.final
                                else None
                            ),
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
                )
        return traces

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


def failed_invocation(request: ModelRequestEnvelope, error_type: str):
    from .external_workflow import NaturalInvocation

    scoring = ScoringResult(
        success=False,
        score=0.0,
        method="provider_failure_intention_to_treat",
        normalized_output="",
        normalized_expected="",
        details={"error_type": error_type},
    )
    return NaturalInvocation(
        request=request,
        response=ProviderResponse(
            content="",
            usage=ProviderUsage(),
            response_id=None,
        ),
        final=True,
        scoring=scoring,
    )
