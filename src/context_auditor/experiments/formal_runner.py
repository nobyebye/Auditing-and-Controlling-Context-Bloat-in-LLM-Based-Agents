"""Real-provider formal experiment runner."""

from __future__ import annotations

import json
import hashlib
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
from context_auditor.application import ApplyMitigation, CaptureContext
from context_auditor.application.analysis import AnalyzeBloat
from context_auditor.application.reporting import BuildReport
from context_auditor.domain.models import (
    CaptureRequest,
    ModelRequestEnvelope,
    ProviderUsage,
)
from context_auditor.ports import ChatProvider

from .config import ExperimentConfig
from .formal_workflow import execute_formal_workflow
from .scoring import score_response


class RunFormalExperiment:
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

    def execute(self, config: ExperimentConfig, run_id: str | None = None) -> Path:
        if config.provider != "mock":
            require_clean_git_worktree(self.project_root)
        provider = self.provider_override or build_provider(config)
        if provider.provider_name != config.provider or provider.model != config.model:
            raise ValueError("Provider identity does not match the formal experiment config")
        data = self.datasets.load(config.dataset_name, config.dataset_version)
        paths, manifest = self.registry.create(
            experiment_id=config.experiment_id,
            framework=config.framework,
            provider=config.provider,
            model=config.model,
            config_path=self._portable_config_path(config.source_path),
            config_hash=config.config_hash,
            dataset_name=config.dataset_name,
            dataset_version=config.dataset_version,
            dataset_hash=self.datasets.content_hash(
                config.dataset_name, config.dataset_version
            ),
            seed=config.seed,
            repetition_id=0,
            run_id=run_id,
        )
        logger, handler = configure_log(paths.log, manifest.run_id)
        try:
            traces = self._run(config, data, provider, paths.traces, manifest.run_id, logger)
            summary = AnalyzeBloat().execute(traces)
            rules = json.loads(
                (
                    self.project_root
                    / "configs"
                    / "conclusions"
                    / "rq_rules_v1.json"
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
            logger.info("formal_run_completed traces=%d", len(traces))
            handler.flush()
            self.registry.complete(paths, manifest, aggregate_usage(traces))
            return paths.root
        except Exception as error:
            logger.exception("formal_run_failed")
            handler.flush()
            self.registry.fail(paths, manifest, f"{type(error).__name__}: {error}")
            raise
        finally:
            logger.removeHandler(handler)
            handler.close()

    def _run(
        self,
        config: ExperimentConfig,
        data: dict,
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
            near_duplicate_threshold=config.near_duplicate_threshold,
            relevance_threshold=config.relevance_threshold,
        )
        mitigation = ApplyMitigation(self.tokenizer)
        langchain = LangChainRuntime(provider) if config.framework == "langchain" else None
        traces = []

        def invoke(messages):
            for attempt in range(config.generation.max_retries + 1):
                try:
                    envelope = ModelRequestEnvelope(
                        messages=messages,
                        generation_parameters=config.generation,
                    )
                    if langchain:
                        response, captured = langchain.invoke(envelope)
                    else:
                        response, captured = provider.invoke(envelope), messages
                    captured_envelope = replace(envelope, messages=captured)
                    capture_hash = hashlib.sha256(
                        canonical_payload_bytes(
                            build_openai_payload(captured_envelope, config.model)
                        )
                    ).hexdigest()
                    return (
                        response,
                        captured,
                        attempt,
                        captured_envelope,
                        capture_hash,
                    )
                except Exception:
                    if attempt >= config.generation.max_retries:
                        raise
                    delay = min(8.0, 2.0**attempt)
                    logger.warning("provider_retry attempt=%d delay=%.1f", attempt + 1, delay)
                    time.sleep(delay)
            raise RuntimeError("Provider retry loop exited unexpectedly")

        selected_tasks = [
            task
            for task in data["tasks"]
            if config.dataset_split == "all"
            or task.get("split", "test") == config.dataset_split
        ]
        if config.task_ids:
            allowed = set(config.task_ids)
            selected_tasks = [
                task for task in selected_tasks if task["task_id"] in allowed
            ]
            missing = sorted(allowed - {task["task_id"] for task in selected_tasks})
            if missing:
                raise ValueError(
                    "Configured task IDs are missing from the selected split: "
                    + ", ".join(missing)
                )
        for repetition in range(config.repetitions):
            for task in selected_tasks:
                workflow = task["workflow_family"]
                for condition in config.workflows.get(workflow, ()):
                    invocations = execute_formal_workflow(
                        task,
                        condition,
                        data,
                        config.framework,
                        mitigation,
                        invoke,
                    )
                    for invocation_index, invocation in enumerate(invocations):
                        scoring = (
                            score_response(task, invocation.response.content)
                            if invocation.final
                            else None
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
                                    configuration=condition.name,
                                    workflow_family=workflow,
                                    dataset_name=config.dataset_name,
                                    dataset_version=config.dataset_version,
                                    repetition_id=repetition,
                                    seed=config.seed + repetition,
                                    invocation_index=invocation_index,
                                    messages=invocation.messages,
                                    config_hash=config.config_hash,
                                    request_envelope=invocation.request_envelope,
                                    provider_request=invocation.response.request_record,
                                    framework_capture_hash=invocation.framework_capture_hash,
                                    evidence_tier="controlled",
                                    dataset_split=task.get("split", "test"),
                                    analysis_cohort=config.analysis_cohort,
                                    task_success=scoring.success if scoring else None,
                                    task_output=(
                                        invocation.response.content
                                        if invocation.final
                                        else None
                                    ),
                                    expected_answer=task["expected_answer"],
                                    provider_usage=invocation.response.usage,
                                    latency_ms=invocation.response.latency_ms,
                                    attempt_index=invocation.attempt_index,
                                    generation_parameters=config.generation,
                                    scoring=scoring,
                                    mitigation_decisions=invocation.mitigation_decisions,
                                    privacy_mode=config.privacy_mode,
                                )
                            )
                        )
        if not traces:
            raise ValueError("Formal experiment selected no tasks")
        return traces

    def _portable_config_path(self, path: Path) -> Path:
        try:
            return path.resolve().relative_to(self.project_root.resolve())
        except ValueError:
            return path.resolve()


def build_provider(config: ExperimentConfig) -> ChatProvider:
    if config.provider == "mock":
        return MockProvider(config.model)
    if config.provider == "deepseek":
        return DeepSeekProvider.from_environment(config.model, config.generation)
    raise ValueError(f"Unsupported formal provider: {config.provider}")


def aggregate_usage(traces: list) -> ProviderUsage:
    usages = [trace.provider_usage for trace in traces if trace.provider_usage]
    return ProviderUsage(
        input_tokens=sum(item.input_tokens or 0 for item in usages),
        output_tokens=sum(item.output_tokens or 0 for item in usages),
        total_tokens=sum(item.total_tokens or 0 for item in usages),
        cached_input_tokens=sum(item.cached_input_tokens or 0 for item in usages),
        cost_usd=sum(item.cost_usd or 0.0 for item in usages),
    )


def configure_log(
    path: Path,
    run_id: str,
) -> tuple[logging.Logger, logging.FileHandler]:
    logger = logging.getLogger(f"context_auditor.formal.{run_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger, handler
