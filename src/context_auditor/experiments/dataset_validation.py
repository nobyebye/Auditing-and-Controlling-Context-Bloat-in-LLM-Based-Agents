"""Validation for versioned formal-study datasets."""

from __future__ import annotations

from collections import Counter
from typing import Any


def validate_dataset(data: dict[str, Any]) -> dict[str, Any]:
    tasks = data.get("tasks")
    documents = data.get("documents")
    memories = data.get("memory")
    manifest = data.get("manifest")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("Dataset must contain a non-empty tasks list")
    if not isinstance(documents, list) or not isinstance(memories, list):
        raise ValueError("Dataset documents and memory must be lists")
    if not isinstance(manifest, dict):
        raise ValueError("Dataset manifest must be an object")

    task_ids = [str(task.get("task_id", "")) for task in tasks]
    if any(not task_id for task_id in task_ids):
        raise ValueError("Every task must have a task_id")
    if len(set(task_ids)) != len(task_ids):
        raise ValueError("Task IDs must be unique")
    valid_workflows = {"retrieval_qa", "memory_turns", "multi_step_tool"}
    for task in tasks:
        if task.get("workflow_family") not in valid_workflows:
            raise ValueError(f"Unsupported workflow for task {task['task_id']}")
        if task.get("split") not in {"calibration", "test", "stress"}:
            raise ValueError(f"Invalid split for task {task['task_id']}")
        if not task.get("prompt") or "expected_answer" not in task:
            raise ValueError(f"Task {task['task_id']} is missing prompt or expected answer")
        if task["workflow_family"] == "multi_step_tool" and "tool" not in task:
            raise ValueError(f"Tool task {task['task_id']} is missing a tool result")

    source_task_ids = {
        task_id
        for source in [*documents, *memories]
        for task_id in source.get("relevant_task_ids", [])
    }
    required_source_ids = {
        task["task_id"]
        for task in tasks
        if task["workflow_family"] in {"retrieval_qa", "memory_turns"}
    }
    missing_sources = sorted(required_source_ids - source_task_ids)
    if missing_sources:
        raise ValueError(
            "Tasks without a relevant retrieval or memory source: "
            + ", ".join(missing_sources)
        )

    split_counts = Counter(task["split"] for task in tasks)
    workflow_counts = Counter(task["workflow_family"] for task in tasks)
    declared_count = manifest.get("task_count")
    if declared_count is not None and int(declared_count) != len(tasks):
        raise ValueError("Dataset manifest task_count does not match tasks.json")
    return {
        "valid": True,
        "task_count": len(tasks),
        "split_counts": dict(sorted(split_counts.items())),
        "workflow_counts": dict(sorted(workflow_counts.items())),
        "document_count": len(documents),
        "memory_count": len(memories),
    }
