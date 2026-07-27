"""Condition-blind task-outcome annotation for Study C mitigation outputs."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from context_auditor.adapters.storage.jsonl import trace_from_dict
from context_auditor.adapters.storage.runs import file_hash
from context_auditor.adapters.storage.serialization import write_json_atomic
from context_auditor.application.agreement import annotation_agreement
from context_auditor.application.external_annotations import (
    opaque_id,
    read_csv,
    user_prompt,
    write_csv,
)
from context_auditor.domain.models import AuditTrace, SCHEMA_VERSION

OUTCOME_DECISIONS = frozenset({"success", "failure", "uncertain"})
OUTCOME_FIELDS = (
    "output_key",
    "task_prompt",
    "expected_answer",
    "model_output",
    "decision",
    "confidence_1_to_5",
    "notes",
)


def export_outcome_annotation_packages(
    traces_path: str | Path,
    output_dir: str | Path,
    *,
    annotation_set_id: str,
) -> Path:
    source = Path(traces_path)
    traces = load_trace_file(source)
    selected = [
        trace
        for trace in traces
        if trace.evidence_tier == "mitigation" and trace.task_success is not None
    ]
    if not selected:
        raise ValueError("No Study C mitigation outputs were found")
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"Outcome annotation output exists: {destination}")
    rows = []
    answer_key = []
    for trace in sorted(selected, key=lambda item: item.trace_id):
        output_key = opaque_id(annotation_set_id, trace.trace_id)
        rows.append(
            {
                "output_key": output_key,
                "task_prompt": user_prompt(trace),
                "expected_answer": trace.expected_answer or "",
                "model_output": trace.task_output or "",
                "decision": "",
                "confidence_1_to_5": "",
                "notes": "",
            }
        )
        answer_key.append(
            {
                "output_key": output_key,
                "trace_id": trace.trace_id,
                "task_id": trace.task_id,
                "framework": trace.framework,
                "workflow_family": trace.workflow_family,
                "configuration": trace.configuration,
                "automatic_success": str(bool(trace.task_success)).lower(),
                "automatic_score": (
                    trace.scoring.score if trace.scoring is not None else ""
                ),
            }
        )
    destination.mkdir(parents=True)
    write_csv(destination / "reviewer_a.csv", OUTCOME_FIELDS, rows)
    write_csv(destination / "reviewer_b.csv", OUTCOME_FIELDS, rows)
    write_csv(
        destination / "answer_key.csv",
        tuple(answer_key[0]),
        answer_key,
    )
    write_json_atomic(
        destination / "annotation_manifest.json",
        {
            "schema_version": SCHEMA_VERSION,
            "annotation_set_id": annotation_set_id,
            "source_trace_sha256": file_hash(source),
            "output_count": len(rows),
            "reviewer_overlap": "100%",
            "decision_values": sorted(OUTCOME_DECISIONS),
            "hidden_from_reviewers": [
                "trace_id",
                "task_id",
                "framework",
                "workflow_family",
                "configuration",
                "automatic_success",
                "automatic_score",
            ],
        },
    )
    return destination


def adjudicate_outcome_files(
    reviewer_a_path: str | Path,
    reviewer_b_path: str | Path,
    answer_key_path: str | Path,
    output_dir: str | Path,
    *,
    annotation_set_id: str,
) -> Path:
    reviewer_a = completed_outcomes(read_csv(Path(reviewer_a_path)))
    reviewer_b = completed_outcomes(read_csv(Path(reviewer_b_path)))
    answer_key = {
        row["output_key"]: row for row in read_csv(Path(answer_key_path))
    }
    if set(reviewer_a) != set(reviewer_b):
        raise ValueError("Both reviewers must complete the same output keys")
    agreement = annotation_agreement(
        outcome_rows_for_agreement(reviewer_a.values()),
        outcome_rows_for_agreement(reviewer_b.values()),
    )
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"Outcome adjudication output exists: {destination}")
    destination.mkdir(parents=True)
    rows = []
    for key in sorted(reviewer_a):
        if key not in answer_key:
            raise ValueError(f"Unknown output key: {key}")
        left = reviewer_a[key]
        right = reviewer_b[key]
        agreed = left["decision"] == right["decision"]
        rows.append(
            {
                "output_key": key,
                "reviewer_a_decision": left["decision"],
                "reviewer_b_decision": right["decision"],
                "adjudicated_decision": left["decision"] if agreed else "",
                "adjudication_notes": "" if agreed else "REQUIRES_CONSENSUS",
            }
        )
    write_csv(
        destination / "adjudication.csv",
        tuple(rows[0]),
        rows,
    )
    write_json_atomic(destination / "agreement.json", agreement)
    write_json_atomic(
        destination / "adjudication_manifest.json",
        {
            "schema_version": SCHEMA_VERSION,
            "annotation_set_id": annotation_set_id,
            "output_count": len(rows),
            "unresolved_count": sum(
                not row["adjudicated_decision"] for row in rows
            ),
        },
    )
    return destination


def load_outcome_consensus(
    adjudication_path: str | Path,
    answer_key_path: str | Path,
) -> dict[str, bool]:
    answer_key = {
        row["output_key"]: row for row in read_csv(Path(answer_key_path))
    }
    result = {}
    for row in read_csv(Path(adjudication_path)):
        decision = row.get("adjudicated_decision", "").strip().lower()
        if decision not in {"success", "failure"}:
            raise ValueError(
                "Outcome adjudication must resolve to success or failure: "
                + row.get("output_key", "")
            )
        key = answer_key.get(row["output_key"])
        if key is None:
            raise ValueError(f"Unknown adjudicated output: {row['output_key']}")
        result[key["trace_id"]] = decision == "success"
    return result


def completed_outcomes(
    rows: Iterable[dict[str, str]],
) -> dict[str, dict[str, str]]:
    result = {}
    for row in rows:
        key = row.get("output_key", "").strip()
        decision = row.get("decision", "").strip().lower()
        confidence = row.get("confidence_1_to_5", "").strip()
        if not key or decision not in OUTCOME_DECISIONS:
            raise ValueError(f"Incomplete outcome annotation: {key}")
        if confidence not in {"1", "2", "3", "4", "5"}:
            raise ValueError(f"Invalid confidence for {key}: {confidence}")
        result[key] = {**row, "decision": decision}
    return result


def outcome_rows_for_agreement(
    rows: Iterable[dict[str, str]],
) -> list[dict[str, str]]:
    decision_map = {
        "success": "keep",
        "failure": "remove",
        "uncertain": "uncertain",
    }
    return [
        {
            "segment_key": row["output_key"],
            "decision": decision_map[row["decision"]],
            "reasons": "",
        }
        for row in rows
    ]


def load_trace_file(path: Path) -> list[AuditTrace]:
    with path.open(encoding="utf-8") as handle:
        return [
            trace_from_dict(json.loads(line))
            for line in handle
            if line.strip()
        ]
