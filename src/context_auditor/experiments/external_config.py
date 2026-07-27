"""Configuration contract for independently validated natural-trace runs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from context_auditor.domain.enums import PrivacyMode
from context_auditor.domain.models import GenerationParameters, SCHEMA_VERSION


@dataclass(frozen=True)
class ExternalValidationConfig:
    schema_version: str
    experiment_id: str
    dataset_name: str
    dataset_version: str
    dataset_split: str
    framework: str
    provider: str
    model: str
    seed: int
    retrieval_top_k: int
    memory_top_k: int
    max_tool_invocations: int
    call_budget: int
    call_ledger_path: str
    privacy_mode: PrivacyMode
    generation: GenerationParameters
    task_ids: tuple[str, ...]
    source_path: Path
    config_hash: str


def load_external_validation_config(
    path: str | Path,
) -> ExternalValidationConfig:
    source = Path(path)
    raw = source.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"External config must use schema {SCHEMA_VERSION}"
        )
    required = {
        "experiment_id",
        "dataset_name",
        "dataset_version",
        "framework",
        "provider",
        "model",
    }
    missing = sorted(required - data.keys())
    if missing:
        raise ValueError("Missing external config fields: " + ", ".join(missing))
    max_tool_invocations = int(data.get("max_tool_invocations", 2))
    if max_tool_invocations not in {1, 2}:
        raise ValueError("max_tool_invocations must be 1 or 2")
    return ExternalValidationConfig(
        schema_version=SCHEMA_VERSION,
        experiment_id=str(data["experiment_id"]),
        dataset_name=str(data["dataset_name"]),
        dataset_version=str(data["dataset_version"]),
        dataset_split=str(data.get("dataset_split", "test")),
        framework=str(data["framework"]),
        provider=str(data["provider"]),
        model=str(data["model"]),
        seed=int(data.get("seed", 20260727)),
        retrieval_top_k=int(data.get("retrieval_top_k", 5)),
        memory_top_k=int(data.get("memory_top_k", 8)),
        max_tool_invocations=max_tool_invocations,
        call_budget=int(data.get("call_budget", 500)),
        call_ledger_path=str(
            data.get(
                "call_ledger_path",
                "runs/studies/external-validation-v1.2-call-ledger.jsonl",
            )
        ),
        privacy_mode=PrivacyMode(data.get("privacy_mode", "redacted")),
        generation=GenerationParameters(**data.get("generation", {})),
        task_ids=tuple(str(item) for item in data.get("task_ids", [])),
        source_path=source,
        config_hash=hashlib.sha256(raw).hexdigest(),
    )
