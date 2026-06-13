"""Experiment configuration loading."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .custom_react import AgentConfig


@dataclass(frozen=True)
class ExperimentConfig:
    experiment_id: str
    run_id: str
    dataset_name: str
    provider: str
    model: str
    output_path: str
    workflow_configs: dict[str, list[AgentConfig]]


def load_experiment_config(path: str | Path) -> ExperimentConfig:
    config_path = Path(path)
    data = json.loads(config_path.read_text(encoding="utf-8"))
    workflow_configs = {
        workflow: [AgentConfig(**item) for item in items]
        for workflow, items in data.get("workflow_configs", {}).items()
    }
    return ExperimentConfig(
        experiment_id=data.get("experiment_id", "pilot"),
        run_id=data.get("run_id", "run-001"),
        dataset_name=data.get("dataset_name", "controlled_synthetic"),
        provider=data.get("provider", "mock"),
        model=data.get("model", "mock-llm"),
        output_path=data.get("output_path", "traces/pilot.jsonl"),
        workflow_configs=workflow_configs,
    )
