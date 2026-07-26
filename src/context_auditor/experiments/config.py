"""Versioned experiment configuration loading and validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from context_auditor.domain.enums import PrivacyMode


@dataclass(frozen=True)
class WorkflowCondition:
    name: str
    retrieval_top_k: int = 0
    include_memory: bool = False
    use_tools: bool = False
    duplicate_retrieval: bool = False
    include_irrelevant_retrieval: bool = False
    duplicate_memory: bool = False
    repeat_tool_output: bool = False
    mitigation_strategy: str = "none"


@dataclass(frozen=True)
class ExperimentConfig:
    schema_version: str
    experiment_id: str
    dataset_name: str
    dataset_version: str
    framework: str
    provider: str
    model: str
    repetitions: int
    seed: int
    privacy_mode: PrivacyMode
    workflows: dict[str, tuple[WorkflowCondition, ...]]
    source_path: Path
    config_hash: str


def load_experiment_config(path: str | Path) -> ExperimentConfig:
    source = Path(path)
    raw = source.read_bytes()
    data: dict[str, Any] = json.loads(raw.decode("utf-8"))
    required = {
        "schema_version",
        "experiment_id",
        "dataset_name",
        "dataset_version",
        "framework",
        "provider",
        "model",
        "workflows",
    }
    missing = sorted(required - data.keys())
    if missing:
        raise ValueError(f"Missing experiment config fields: {', '.join(missing)}")
    workflows = {
        name: tuple(WorkflowCondition(**condition) for condition in conditions)
        for name, conditions in data["workflows"].items()
    }
    if not workflows or any(not conditions for conditions in workflows.values()):
        raise ValueError("Every configured workflow must have at least one condition")
    repetitions = int(data.get("repetitions", 1))
    if repetitions < 1:
        raise ValueError("repetitions must be at least 1")
    return ExperimentConfig(
        schema_version=str(data["schema_version"]),
        experiment_id=str(data["experiment_id"]),
        dataset_name=str(data["dataset_name"]),
        dataset_version=str(data["dataset_version"]),
        framework=str(data["framework"]),
        provider=str(data["provider"]),
        model=str(data["model"]),
        repetitions=repetitions,
        seed=int(data.get("seed", 42)),
        privacy_mode=PrivacyMode(data.get("privacy_mode", "redacted")),
        workflows=workflows,
        source_path=source,
        config_hash=hashlib.sha256(raw).hexdigest(),
    )
