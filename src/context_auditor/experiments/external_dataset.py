"""Prepare a pinned, ID-only external-validation dataset from public sources."""

from __future__ import annotations

import hashlib
import json
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from context_auditor.adapters.storage.serialization import write_json_atomic
from context_auditor.domain.models import SCHEMA_VERSION
from context_auditor.domain.text import redact_text

DEFAULT_SELECTION_SEED = 20260727
BFCL_MAX_TURNS = 2
BFCL_DISTRACTOR_TOOL_COUNT = 8
SOURCE_METADATA = {
    "hotpotqa": {
        "upstream_version": "HotpotQA distractor development set v1",
        "upstream_url": "https://hotpotqa.github.io/",
        "acquisition_url": (
            "https://huggingface.co/datasets/namlh2004/hotpotqa/"
            "resolve/main/hotpot_dev_distractor_v1.json"
        ),
        "license": "CC-BY-SA-4.0",
        "acquired_at": "2026-07-27T10:12:22Z",
    },
    "longmemeval": {
        "upstream_version": "longmemeval-cleaned main commit 98d7416",
        "upstream_url": "https://github.com/xiaowu0162/LongMemEval",
        "acquisition_url": (
            "https://huggingface.co/datasets/xiaowu0162/"
            "longmemeval-cleaned/resolve/main/longmemeval_s_cleaned.json"
        ),
        "license": "MIT",
        "acquired_at": "2026-07-27T10:20:23Z",
    },
    "bfcl": {
        "upstream_version": (
            "BFCL v4 repository commit "
            "6ea57973c7a6097fd7c5915698c54c17c5b1b6c8"
        ),
        "upstream_url": "https://github.com/ShishirPatil/gorilla",
        "acquisition_url": "git sparse checkout",
        "license": "Apache-2.0",
        "acquired_at": "2026-07-27T10:29:31Z",
        "derivation": (
            "First two conversation turns and their reference calls; required "
            "function definitions plus at most eight deterministic distractors."
        ),
    },
}
DATASET_README = """# External Validation Dataset v1

This immutable research view contains 12 calibration tasks and 60 held-out test
tasks: 24 each for retrieval QA, memory, and multi-step tool use. It stores
derived task records selected with seed 20260727 and points back to pinned
HotpotQA, LongMemEval, and BFCL source versions.

Potential credentials, email addresses, and phone numbers in upstream text are
redacted before persistence. Raw third-party source files remain under the
ignored `data/sources/` directory and are not redistributed by this package.
See `dataset_manifest.json` for record IDs, versions, source hashes, and the
derived `tasks.json` hash.
"""
THIRD_PARTY_NOTICES = """# Third-Party Notices

- HotpotQA distractor development set v1, CC-BY-SA-4.0:
  https://hotpotqa.github.io/
- LongMemEval cleaned release, MIT:
  https://github.com/xiaowu0162/LongMemEval
- Berkeley Function Calling Leaderboard (BFCL) v4, Apache-2.0:
  https://github.com/ShishirPatil/gorilla

The dataset directory contains a derived research view. Refer to the upstream
projects for authoritative licensing terms and original data.
"""


def build_bfcl_two_turn_source(
    *,
    tasks_path: str | Path,
    answers_path: str | Path,
    function_docs_dir: str | Path,
    destination: str | Path,
) -> Path:
    """Join the official BFCL files into a pinned two-turn research view."""
    tasks_file = Path(tasks_path)
    answers_file = Path(answers_path)
    docs_dir = Path(function_docs_dir)
    target = Path(destination)
    if target.exists():
        raise FileExistsError(f"Derived BFCL source already exists: {target}")
    tasks = load_records(tasks_file)
    answers = {bfcl_id(item): item for item in load_records(answers_file)}
    tool_docs = load_function_docs(docs_dir)
    derived: list[dict[str, Any]] = []
    for task in tasks:
        task_id = bfcl_id(task)
        answer = answers.get(task_id)
        if answer is None:
            raise ValueError(f"BFCL answer is missing for {task_id}")
        questions = task.get("question", [])[:BFCL_MAX_TURNS]
        ground_truth = answer.get("ground_truth", [])[:BFCL_MAX_TURNS]
        required_names = {
            name
            for call in flatten_bfcl_ground_truth(ground_truth)
            if (name := bfcl_call_name(call))
        }
        excluded = {str(name) for name in task.get("excluded_function", [])}
        matching = [
            doc
            for doc in tool_docs
            if doc["name"] in required_names and doc["name"] not in excluded
        ]
        missing = required_names - {doc["name"] for doc in matching}
        if missing:
            raise ValueError(
                f"BFCL function documents missing for {task_id}: {sorted(missing)}"
            )
        class_markers = [
            str(value).casefold() for value in task.get("involved_classes", [])
        ]
        distractors = [
            doc
            for doc in tool_docs
            if doc["name"] not in required_names
            and doc["name"] not in excluded
            and any(
                marker in doc.get("description", "").casefold()
                for marker in class_markers
            )
        ][:BFCL_DISTRACTOR_TOOL_COUNT]
        derived.append(
            {
                **task,
                "question": questions,
                "ground_truth": ground_truth,
                "function": [*matching, *distractors],
                "upstream_turn_count": len(task.get("question", [])),
                "derivation": {
                    "name": "first-two-turns",
                    "version": "1.0.0",
                    "max_turns": BFCL_MAX_TURNS,
                    "distractor_tool_count": len(distractors),
                },
            }
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as handle:
        for item in derived:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    return target


def prepare_external_validation_dataset(
    *,
    hotpot_path: str | Path,
    longmemeval_path: str | Path,
    bfcl_path: str | Path,
    destination: str | Path,
    seed: int = DEFAULT_SELECTION_SEED,
) -> Path:
    target = Path(destination)
    if target.exists():
        raise FileExistsError(f"External dataset already exists: {target}")
    sources = {
        "hotpotqa": Path(hotpot_path),
        "longmemeval": Path(longmemeval_path),
        "bfcl": Path(bfcl_path),
    }
    for name, path in sources.items():
        if not path.is_file():
            raise FileNotFoundError(f"{name} source is missing: {path}")
    hotpot = load_records(sources["hotpotqa"])
    longmem = load_records(sources["longmemeval"])
    bfcl = load_records(sources["bfcl"])
    selected = [
        *select_and_convert(
            hotpot,
            id_getter=lambda item: str(item["_id"]),
            converter=convert_hotpot,
            calibration_count=4,
            test_count=20,
            seed=seed + 1,
        ),
        *select_balanced_longmem(longmem, seed + 2),
        *select_and_convert(
            [item for item in bfcl if bfcl_max_turns(item) <= 2],
            id_getter=bfcl_id,
            converter=convert_bfcl,
            calibration_count=4,
            test_count=20,
            seed=seed + 3,
        ),
    ]
    selected = [sanitize_external_task(task) for task in selected]
    task_ids = [task["task_id"] for task in selected]
    if len(task_ids) != 72 or len(set(task_ids)) != 72:
        raise ValueError("External selection must contain 72 unique tasks")
    target.mkdir(parents=True)
    write_json_atomic(target / "tasks.json", selected)
    source_manifest = {
        name: {
            "source_path": path.name,
            "sha256": sha256_file(path),
            "record_count": len(records),
            **SOURCE_METADATA[name],
        }
        for (name, path), records in zip(
            sources.items(),
            (hotpot, longmem, bfcl),
        )
    }
    write_json_atomic(
        target / "dataset_manifest.json",
        {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": "external_validation",
            "dataset_version": "v1",
            "selection_seed": seed,
            "calibration_task_count": 12,
            "test_task_count": 60,
            "task_count": 72,
            "tasks_sha256": sha256_file(target / "tasks.json"),
            "sources": source_manifest,
            "selected_task_ids": task_ids,
            "redistribution": (
                "Derived task records are local research artifacts. Public releases "
                "must distribute source IDs and fetch instructions according to each "
                "upstream licence."
            ),
        },
    )
    (target / "README.md").write_text(
        DATASET_README,
        encoding="utf-8",
        newline="\n",
    )
    (target / "THIRD_PARTY_NOTICES.md").write_text(
        THIRD_PARTY_NOTICES,
        encoding="utf-8",
        newline="\n",
    )
    return target


def sanitize_external_task(value: Any) -> Any:
    """Redact credentials and direct identifiers before task persistence."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [sanitize_external_task(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_external_task(item) for item in value)
    if isinstance(value, dict):
        return {
            key: sanitize_external_task(item)
            for key, item in value.items()
        }
    return value


def select_and_convert(
    records: list[dict[str, Any]],
    *,
    id_getter: Callable[[dict[str, Any]], str],
    converter: Callable[[dict[str, Any], str], dict[str, Any]],
    calibration_count: int,
    test_count: int,
    seed: int,
) -> list[dict[str, Any]]:
    if len(records) < calibration_count + test_count:
        raise ValueError("Source dataset has too few eligible records")
    ordered = sorted(records, key=id_getter)
    selected = random.Random(seed).sample(
        ordered,
        calibration_count + test_count,
    )
    return [
        converter(item, "calibration" if index < calibration_count else "test")
        for index, item in enumerate(selected)
    ]


def select_balanced_longmem(
    records: list[dict[str, Any]],
    seed: int,
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in records:
        groups[str(item.get("question_type", "unknown"))].append(item)
    if len(groups) < 3:
        raise ValueError("LongMemEval source lacks question-type diversity")
    generator = random.Random(seed)
    for items in groups.values():
        items.sort(key=lambda item: str(item["question_id"]))
        generator.shuffle(items)
    selected: list[dict[str, Any]] = []
    group_names = sorted(groups)
    while len(selected) < 24:
        progressed = False
        for group in group_names:
            if groups[group] and len(selected) < 24:
                selected.append(groups[group].pop())
                progressed = True
        if not progressed:
            raise ValueError("LongMemEval source has too few eligible records")
    return [
        convert_longmem(
            item,
            "calibration" if index < 4 else "test",
        )
        for index, item in enumerate(selected)
    ]


def convert_hotpot(item: dict[str, Any], split: str) -> dict[str, Any]:
    return {
        "task_id": "hotpot-" + str(item["_id"]),
        "source_dataset": "hotpotqa",
        "source_record_id": str(item["_id"]),
        "workflow_family": "retrieval_qa",
        "split": split,
        "prompt": str(item["question"]),
        "expected_answer": str(item["answer"]),
        "scoring": {"type": "hotpotqa_f1", "minimum_f1": 0.8},
        "documents": [
            {
                "source_id": f"{item['_id']}:{index}",
                "title": str(title),
                "text": " ".join(str(sentence) for sentence in sentences),
            }
            for index, (title, sentences) in enumerate(item["context"])
        ],
    }


def convert_longmem(item: dict[str, Any], split: str) -> dict[str, Any]:
    sessions = []
    for index, turns in enumerate(item.get("haystack_sessions", [])):
        date = (
            item.get("haystack_dates", [None] * len(item["haystack_sessions"]))[
                index
            ]
        )
        sessions.append(
            {
                "source_id": str(
                    item.get("haystack_session_ids", [index])[index]
                ),
                "date": date,
                "text": "\n".join(
                    f"{turn.get('role', 'unknown')}: {turn.get('content', '')}"
                    for turn in turns
                ),
            }
        )
    return {
        "task_id": "longmem-" + str(item["question_id"]),
        "source_dataset": "longmemeval",
        "source_record_id": str(item["question_id"]),
        "workflow_family": "memory_turns",
        "split": split,
        "prompt": str(item["question"]),
        "expected_answer": str(item["answer"]),
        "scoring": {"type": "contains"},
        "question_type": item.get("question_type"),
        "memory_sessions": sessions,
    }


def convert_bfcl(item: dict[str, Any], split: str) -> dict[str, Any]:
    question = item.get("question", "")
    prompt = flatten_bfcl_question(question)
    tools = item.get("function") or item.get("functions") or item.get("tools") or []
    expected_calls = flatten_bfcl_ground_truth(
        item.get("ground_truth", item.get("answer", []))
    )
    return {
        "task_id": "bfcl-" + bfcl_id(item),
        "source_dataset": "bfcl-v4-two-turn-derived",
        "source_record_id": bfcl_id(item),
        "workflow_family": "multi_step_tool",
        "split": split,
        "prompt": prompt,
        "expected_answer": json.dumps(
            item.get("ground_truth", item.get("answer", [])),
            ensure_ascii=False,
            sort_keys=True,
        ),
        "scoring": {"type": "tool_call"},
        "tools": normalize_bfcl_tools(tools),
        "expected_tool_calls": expected_calls,
        "turns": question if isinstance(question, list) else [],
        "derivation": item.get("derivation", {}),
    }


def normalize_bfcl_tools(tools: Any) -> list[dict[str, Any]]:
    result = []
    for tool in tools if isinstance(tools, list) else []:
        function = tool.get("function", tool) if isinstance(tool, dict) else {}
        result.append(
            {
                "name": str(function.get("name", "")),
                "description": str(function.get("description", "")),
                "parameters": normalize_json_schema(
                    function.get("parameters", {})
                ),
            }
        )
    return result


def normalize_json_schema(value: Any) -> Any:
    if isinstance(value, list):
        return [normalize_json_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    normalized = {
        key: normalize_json_schema(item)
        for key, item in value.items()
    }
    type_map = {
        "dict": "object",
        "float": "number",
        "int": "integer",
        "str": "string",
        "String": "string",
        "list": "array",
    }
    if "type" in normalized:
        normalized["type"] = type_map.get(
            str(normalized["type"]),
            normalized["type"],
        )
    return normalized


def flatten_bfcl_question(question: Any) -> str:
    if not isinstance(question, list):
        return str(question)
    contents = []
    for turn in question:
        messages = turn if isinstance(turn, list) else [turn]
        for message in messages:
            if isinstance(message, dict):
                contents.append(str(message.get("content", "")))
            else:
                contents.append(str(message))
    return "\n".join(value for value in contents if value)


def flatten_bfcl_ground_truth(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return [value]
    flattened = []
    for turn in value:
        if isinstance(turn, list):
            flattened.extend(turn)
        else:
            flattened.append(turn)
    return flattened


def bfcl_call_name(value: Any) -> str:
    if isinstance(value, dict):
        if len(value) == 1 and "name" not in value:
            return str(next(iter(value)))
        function = value.get("function", value)
        return str(function.get("name", ""))
    if isinstance(value, str):
        match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", value)
        return match.group(1) if match else ""
    return ""


def load_function_docs(directory: Path) -> list[dict[str, Any]]:
    if not directory.is_dir():
        raise FileNotFoundError(f"BFCL function-doc directory is missing: {directory}")
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        records.extend(load_records(path))
    if not records:
        raise ValueError(f"No BFCL function documents found in {directory}")
    return records


def bfcl_id(item: dict[str, Any]) -> str:
    value = item.get("id", item.get("test_id"))
    if value is None:
        raise ValueError("BFCL record is missing an ID")
    return str(value)


def bfcl_max_turns(item: dict[str, Any]) -> int:
    question = item.get("question", [])
    return len(question) if isinstance(question, list) else 1


def load_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        lines = [line for line in text.splitlines() if line.strip()]
        try:
            return [json.loads(line) for line in lines]
        except json.JSONDecodeError:
            raise ValueError(f"Unsupported source data format: {path}") from error
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "records", "tasks"):
            if isinstance(data.get(key), list):
                return data[key]
    raise ValueError(f"Unsupported source data format: {path}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
