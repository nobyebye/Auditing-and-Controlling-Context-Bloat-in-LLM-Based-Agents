"""Dataset loading for reproducible experiments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .retrieval import Document
from .tasks import Task


@dataclass(frozen=True)
class ControlledDataset:
    name: str
    tasks: list[Task]
    policy_docs: list[Document]
    memory_items: list[str]

    def tasks_by_workflow(self, workflow_family: str) -> list[Task]:
        return [task for task in self.tasks if task.workflow_family == workflow_family]


def load_controlled_dataset(dataset_name: str = "controlled_synthetic") -> ControlledDataset:
    root = Path(__file__).resolve().parents[1] / "datasets" / dataset_name
    tasks = [Task(**item) for item in _load_json(root / "tasks.json")]
    docs = [Document(**item) for item in _load_json(root / "policy_docs.json")]
    memory_items = list(_load_json(root / "memory_items.json"))
    return ControlledDataset(
        name=dataset_name,
        tasks=tasks,
        policy_docs=docs,
        memory_items=memory_items,
    )


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))
