"""Pilot experiment runner."""

from __future__ import annotations

from pathlib import Path

from context_auditor import RuntimeAuditor

from .config import load_experiment_config
from .custom_react import CustomReactAgent
from .tasks import MEMORY_TASKS, RETRIEVAL_TASKS, TOOL_TASKS


def run_pilot(output_path: str | Path | None = None, config_path: str | Path = "configs/pilot.json") -> None:
    experiment = load_experiment_config(config_path)
    output_path = output_path or experiment.output_path
    output = Path(output_path)
    if output.exists():
        output.unlink()
    auditor = RuntimeAuditor(output)
    agent = CustomReactAgent(
        auditor,
        provider=experiment.provider,
        model=experiment.model,
        experiment_id=experiment.experiment_id,
        run_id=experiment.run_id,
        dataset_name=experiment.dataset_name,
    )

    for task in RETRIEVAL_TASKS:
        for config in experiment.workflow_configs["retrieval_qa"]:
            agent.run(task, config)

    for task in MEMORY_TASKS:
        for config in experiment.workflow_configs["memory_turns"]:
            agent.run(task, config)

    for task in TOOL_TASKS:
        for config in experiment.workflow_configs["multi_step_tool"]:
            agent.run(task, config)
