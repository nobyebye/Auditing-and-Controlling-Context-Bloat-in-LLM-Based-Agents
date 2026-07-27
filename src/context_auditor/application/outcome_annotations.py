"""Condition-blind task-outcome annotation for Study C mitigation outputs."""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path
from typing import Iterable

from context_auditor.adapters.storage.jsonl import trace_from_dict
from context_auditor.adapters.storage.runs import file_hash
from context_auditor.adapters.storage.serialization import write_json_atomic
from context_auditor.application.agreement import annotation_agreement
from context_auditor.application.annotation_workbooks import (
    read_annotation_workbooks,
    write_annotation_workbook,
)
from context_auditor.application.external_annotations import (
    opaque_id,
    read_csv,
    user_prompt,
    write_csv,
)
from context_auditor.domain.models import AuditTrace, SCHEMA_VERSION

OUTCOME_DECISIONS = frozenset({"success", "failure", "uncertain"})
OUTCOME_FIELDS = (
    "block_id",
    "block_started_at",
    "block_completed_at",
    "output_key",
    "task_prompt",
    "expected_answer",
    "model_output",
    "decision",
    "confidence_1_to_5",
    "notes",
)


def export_outcome_annotation_packages(
    traces_path: str | Path | Iterable[str | Path],
    output_dir: str | Path,
    *,
    annotation_set_id: str,
    evidence_tiers: tuple[str, ...] = ("counterfactual", "mitigation"),
    configurations: tuple[str, ...] = (),
    outputs_per_block: int = 24,
) -> Path:
    sources = normalize_trace_paths(traces_path)
    traces = [
        trace
        for source in sources
        for trace in load_trace_file(source)
    ]
    selected = [
        trace
        for trace in traces
        if trace.evidence_tier in evidence_tiers
        and trace.task_success is not None
        and (
            not configurations or trace.configuration in configurations
        )
    ]
    if not selected:
        raise ValueError("No matching task outputs were found")
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
    for reviewer in ("a", "b"):
        shuffled = list(rows)
        random.Random(f"{annotation_set_id}:{reviewer}").shuffle(shuffled)
        ordered = []
        blocks = []
        for index in range(0, len(shuffled), outputs_per_block):
            block_id = f"block_{index // outputs_per_block + 1:02d}"
            block_rows = [
                {
                    **row,
                    "block_id": block_id,
                    "block_started_at": "",
                    "block_completed_at": "",
                }
                for row in shuffled[index : index + outputs_per_block]
            ]
            ordered.extend(block_rows)
            blocks.append((block_id, block_rows))
        write_csv(
            destination / f"reviewer_{reviewer}.csv",
            OUTCOME_FIELDS,
            ordered,
        )
        block_dir = destination / f"reviewer_{reviewer}_blocks"
        for block_id, block_rows in blocks:
            write_annotation_workbook(
                block_dir / f"{block_id}.xlsx",
                fields=OUTCOME_FIELDS,
                rows=block_rows,
                block_id=block_id,
                decision_values=tuple(sorted(OUTCOME_DECISIONS)),
            )
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
            "source_trace_sha256": {
                str(source): file_hash(source)
                for source in sources
            },
            "output_count": len(rows),
            "evidence_tiers": list(evidence_tiers),
            "configurations": list(configurations),
            "outputs_per_block": outputs_per_block,
            "reviewer_order_randomized_independently": True,
            "session_rule": {
                "maximum_blocks_per_session": 2,
                "minimum_break_minutes": 10,
            },
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
    reviewer_a = completed_outcomes(
        read_annotation_workbooks(reviewer_a_path)
    )
    reviewer_b = completed_outcomes(
        read_annotation_workbooks(reviewer_b_path)
    )
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
            "block_id": row.get("block_id", ""),
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


def normalize_trace_paths(
    value: str | Path | Iterable[str | Path],
) -> list[Path]:
    if isinstance(value, (str, Path)):
        paths = [Path(value)]
    else:
        paths = [Path(item) for item in value]
    if not paths:
        raise ValueError("At least one trace file is required")
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Trace files are missing: {missing}")
    return paths


def build_outcome_validation_evidence(
    traces_path: str | Path,
    adjudication_path: str | Path,
    answer_key_path: str | Path,
    output_path: str | Path,
) -> Path:
    from context_auditor.application.study_c_evidence import scorer_validation

    traces = load_trace_file(Path(traces_path))
    consensus = load_outcome_consensus(adjudication_path, answer_key_path)
    selected = [trace for trace in traces if trace.trace_id in consensus]
    if set(consensus) != {trace.trace_id for trace in selected}:
        raise ValueError("Outcome consensus refers to missing traces")
    target = Path(output_path)
    if target.exists():
        raise FileExistsError(f"Outcome validation evidence exists: {target}")
    write_json_atomic(
        target,
        {
            "schema_version": SCHEMA_VERSION,
            "human_reference_type": "double_reviewed_adjudicated_task_success",
            "automatic_scorer_validation": scorer_validation(
                selected,
                consensus,
            ),
        },
    )
    return target
