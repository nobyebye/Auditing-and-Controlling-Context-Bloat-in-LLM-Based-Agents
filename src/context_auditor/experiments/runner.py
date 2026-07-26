"""End-to-end experiment use case."""

from __future__ import annotations

import logging
from pathlib import Path

from context_auditor.adapters.common import DefaultIdGenerator, RegexTokenizer, UtcClock
from context_auditor.adapters.frameworks import LangChainCaptureCallback, LangChainContextAdapter
from context_auditor.adapters.storage import FileDatasetRepository, JsonlTraceRepository, RunRegistry
from context_auditor.application import ApplyMitigation, CaptureContext
from context_auditor.application.analysis import AnalyzeBloat
from context_auditor.application.reporting import BuildReport
from context_auditor.domain.models import CaptureRequest

from .config import ExperimentConfig
from .workflow import execute_workflow


class RunExperiment:
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root)
        self.tokenizer = RegexTokenizer()
        self.datasets = FileDatasetRepository(self.project_root / "data")
        self.registry = RunRegistry(self.project_root / "runs")

    def execute(self, config: ExperimentConfig, run_id: str | None = None) -> Path:
        if config.provider != "mock":
            raise ValueError(
                "The controlled experiment runner supports only the mock provider. "
                "Use a dedicated real-model experiment command to avoid mislabeled traces."
            )
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
            dataset_hash=self.datasets.content_hash(config.dataset_name, config.dataset_version),
            seed=config.seed,
            repetition_id=0,
            run_id=run_id,
        )
        logger, handler = self._configure_log(paths.log, manifest.run_id)
        logger.info("run_started id=%s", manifest.run_id)
        try:
            traces = self._run_conditions(config, data, paths.traces, manifest.run_id)
            summary = AnalyzeBloat().execute(traces)
            BuildReport().execute(
                traces,
                summary,
                invocation_csv=paths.invocation_metrics,
                task_csv=paths.task_metrics,
                summary_json=paths.summary,
                tables_dir=paths.tables,
                figures_dir=paths.figures,
            )
            logger.info("run_completed traces=%d", len(traces))
            handler.flush()
            self.registry.complete(paths, manifest)
            return paths.root
        except Exception as error:
            logger.exception("run_failed")
            handler.flush()
            self.registry.fail(paths, manifest, f"{type(error).__name__}: {error}")
            raise
        finally:
            logger.removeHandler(handler)
            handler.close()

    def _run_conditions(
        self,
        config: ExperimentConfig,
        data: dict,
        trace_path: Path,
        run_id: str,
    ) -> list:
        langchain_adapter = LangChainContextAdapter() if config.framework == "langchain" else None
        repository = JsonlTraceRepository(trace_path)
        capture = CaptureContext(repository, self.tokenizer, UtcClock(), DefaultIdGenerator())
        mitigation = ApplyMitigation(self.tokenizer)
        traces = []
        for repetition in range(config.repetitions):
            for workflow, conditions in config.workflows.items():
                tasks = [task for task in data["tasks"] if task["workflow_family"] == workflow]
                for task in tasks:
                    for condition in conditions:
                        state = execute_workflow(
                            task,
                            condition,
                            data["documents"],
                            data["memory"],
                            mitigation,
                        )
                        for invocation_index, messages in enumerate(state.snapshots):
                            final = invocation_index == len(state.snapshots) - 1
                            request = CaptureRequest(
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
                                messages=messages,
                                config_hash=config.config_hash,
                                task_success=state.success if final else None,
                                task_output=state.answer if final else None,
                                expected_answer=task["expected_answer"],
                                mitigation_decisions=state.mitigation_decisions if final else (),
                                privacy_mode=config.privacy_mode,
                            )
                            if langchain_adapter:
                                langchain_messages = to_langchain_messages(messages)
                                callback = LangChainCaptureCallback(
                                    capture,
                                    lambda converted, template=request: replace_messages(
                                        template, converted
                                    ),
                                )
                                callback.on_chat_model_start({}, [langchain_messages])
                                traces.extend(callback.captured)
                            else:
                                traces.append(capture.execute(request))
        return traces

    @staticmethod
    def _configure_log(path: Path, run_id: str) -> tuple[logging.Logger, logging.FileHandler]:
        logger = logging.getLogger(f"context_auditor.run.{run_id}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        return logger, handler

    def _portable_config_path(self, path: Path) -> Path:
        try:
            return path.resolve().relative_to(self.project_root.resolve())
        except ValueError:
            return path.resolve()


def replace_messages(
    request: CaptureRequest,
    messages: tuple,
) -> CaptureRequest:
    from dataclasses import replace

    return replace(request, messages=messages)


def to_langchain_messages(messages: tuple) -> list:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

    converted = []
    for message in messages:
        additional_kwargs = dict(message.metadata)
        if message.role == "system":
            converted.append(
                SystemMessage(content=message.content, additional_kwargs=additional_kwargs)
            )
        elif message.role == "user":
            converted.append(
                HumanMessage(content=message.content, additional_kwargs=additional_kwargs)
            )
        elif message.role == "assistant":
            converted.append(
                AIMessage(content=message.content, additional_kwargs=additional_kwargs)
            )
        elif message.role == "tool":
            converted.append(
                ToolMessage(
                    content=message.content,
                    tool_call_id="controlled-tool-call",
                    additional_kwargs=additional_kwargs,
                )
            )
        else:
            converted.append(
                HumanMessage(content=message.content, additional_kwargs=additional_kwargs)
            )
    return converted
