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
    randomization_seed: int
    retrieval_top_k: int
    memory_top_k: int
    max_provider_invocations_per_tool_cell: int
    near_duplicate_threshold: float
    relevance_threshold: float
    verbose_tool_token_threshold: int
    source_dominance_threshold: float
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
        "near_duplicate_threshold",
        "relevance_threshold",
        "verbose_tool_token_threshold",
        "source_dominance_threshold",
    }
    missing = sorted(required - data.keys())
    if missing:
        raise ValueError("Missing external config fields: " + ", ".join(missing))
    provider_cap = int(
        data.get("max_provider_invocations_per_tool_cell", 2)
    )
    if provider_cap not in {1, 2}:
        raise ValueError(
            "max_provider_invocations_per_tool_cell must be 1 or 2"
        )
    generation = GenerationParameters(**data.get("generation", {}))
    if generation.max_retries != 0:
        raise ValueError("External validation requires max_retries=0")
    if generation.thinking != "disabled":
        raise ValueError("External validation requires thinking=disabled")
    near_duplicate_threshold = float(
        data.get("near_duplicate_threshold", 0.80)
    )
    relevance_threshold = float(data.get("relevance_threshold", 0.05))
    verbose_tool_token_threshold = int(
        data.get("verbose_tool_token_threshold", 80)
    )
    source_dominance_threshold = float(
        data.get("source_dominance_threshold", 0.65)
    )
    if not 0.0 <= near_duplicate_threshold <= 1.0:
        raise ValueError("near_duplicate_threshold must be between 0 and 1")
    if not 0.0 <= relevance_threshold <= 1.0:
        raise ValueError("relevance_threshold must be between 0 and 1")
    if verbose_tool_token_threshold < 1:
        raise ValueError("verbose_tool_token_threshold must be positive")
    if not 0.0 <= source_dominance_threshold <= 1.0:
        raise ValueError("source_dominance_threshold must be between 0 and 1")
    return ExternalValidationConfig(
        schema_version=SCHEMA_VERSION,
        experiment_id=str(data["experiment_id"]),
        dataset_name=str(data["dataset_name"]),
        dataset_version=str(data["dataset_version"]),
        dataset_split=str(data.get("dataset_split", "test")),
        framework=str(data["framework"]),
        provider=str(data["provider"]),
        model=str(data["model"]),
        randomization_seed=int(
            data.get("randomization_seed", 20260727)
        ),
        retrieval_top_k=int(data.get("retrieval_top_k", 5)),
        memory_top_k=int(data.get("memory_top_k", 8)),
        max_provider_invocations_per_tool_cell=provider_cap,
        near_duplicate_threshold=near_duplicate_threshold,
        relevance_threshold=relevance_threshold,
        verbose_tool_token_threshold=verbose_tool_token_threshold,
        source_dominance_threshold=source_dominance_threshold,
        call_budget=int(data.get("call_budget", 500)),
        call_ledger_path=str(
            data.get(
                "call_ledger_path",
                "runs/studies/external-validation-v1.2.1-call-ledger.jsonl",
            )
        ),
        privacy_mode=PrivacyMode(data.get("privacy_mode", "redacted")),
        generation=generation,
        task_ids=tuple(str(item) for item in data.get("task_ids", [])),
        source_path=source,
        config_hash=hashlib.sha256(raw).hexdigest(),
    )
