"""Double-blind segment annotation export, validation, and adjudication."""

from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from context_auditor.adapters.storage.jsonl import trace_from_dict
from context_auditor.adapters.storage.runs import file_hash
from context_auditor.adapters.storage.serialization import write_json_atomic
from context_auditor.application.agreement import (
    VALID_DECISIONS,
    annotation_agreement,
)
from context_auditor.application.study_bundle import validate_study_bundle
from context_auditor.domain.models import AuditTrace, ReferenceAnnotation, SCHEMA_VERSION

ANNOTATION_REASONS = frozenset(
    {
        "exact_duplicate",
        "near_duplicate",
        "low_query_relevance",
        "stale_context",
        "verbose_tool_output",
        "other",
    }
)

REVIEW_FIELDS = (
    "sample_id",
    "segment_key",
    "task_prompt",
    "message_index",
    "role",
    "segment_ordinal",
    "segment_text",
    "decision",
    "reasons",
    "confidence_1_to_5",
    "notes",
)


def export_context_annotation_packages(
    bundle_path: str | Path,
    output_dir: str | Path,
    *,
    annotation_set_id: str,
    include_splits: tuple[str, ...] = ("test",),
) -> Path:
    bundle = Path(bundle_path)
    validate_study_bundle(bundle)
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"Annotation output already exists: {destination}")
    traces, manifest = load_bundle(bundle)
    selected = [
        trace
        for trace in traces
        if trace.task_success is not None
        and trace.dataset_split in include_splits
        and trace.evidence_tier == "natural"
    ]
    if not selected:
        raise ValueError("The bundle has no final natural-evidence traces")
    rows: list[dict[str, object]] = []
    answer_key: list[dict[str, object]] = []
    for trace in sorted(
        selected,
        key=lambda item: (item.task_id, item.framework, item.trace_id),
    ):
        sample_id = opaque_id(annotation_set_id, trace.trace_id)
        prompt = user_prompt(trace)
        for segment in trace.segments:
            segment_key = opaque_id(
                annotation_set_id,
                f"{trace.trace_id}:{segment.segment_id}",
            )
            rows.append(
                {
                    "sample_id": sample_id,
                    "segment_key": segment_key,
                    "task_prompt": prompt,
                    "message_index": segment.message_index,
                    "role": segment.role,
                    "segment_ordinal": segment.ordinal,
                    "segment_text": segment.text,
                    "decision": "",
                    "reasons": "",
                    "confidence_1_to_5": "",
                    "notes": "",
                }
            )
            answer_key.append(
                {
                    "sample_id": sample_id,
                    "segment_key": segment_key,
                    "trace_id": trace.trace_id,
                    "task_id": trace.task_id,
                    "framework": trace.framework,
                    "workflow_family": trace.workflow_family,
                    "segment_id": segment.segment_id,
                    "source_type": segment.source_type,
                    "token_count": segment.token_count,
                    "detected_labels": ";".join(
                        trace.detected_labels.get(segment.segment_id, ())
                    ),
                }
            )
    destination.mkdir(parents=True)
    write_csv(destination / "reviewer_a.csv", REVIEW_FIELDS, rows)
    write_csv(destination / "reviewer_b.csv", REVIEW_FIELDS, rows)
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
            "source_study_id": manifest["study_id"],
            "source_bundle_sha256": file_hash(bundle),
            "trace_count": len(selected),
            "segment_count": len(rows),
            "reviewer_overlap": "100%",
            "include_splits": list(include_splits),
            "decision_values": sorted(VALID_DECISIONS),
            "reason_values": sorted(ANNOTATION_REASONS),
            "hidden_from_reviewers": [
                "trace_id",
                "task_id",
                "framework",
                "workflow_family",
                "source_type",
                "detected_labels",
                "task_output",
                "task_success",
            ],
        },
    )
    return destination


def adjudicate_annotation_files(
    reviewer_a_path: str | Path,
    reviewer_b_path: str | Path,
    answer_key_path: str | Path,
    output_dir: str | Path,
    *,
    annotation_set_id: str,
) -> Path:
    reviewer_a = read_csv(Path(reviewer_a_path))
    reviewer_b = read_csv(Path(reviewer_b_path))
    answer_key = {row["segment_key"]: row for row in read_csv(Path(answer_key_path))}
    agreement = annotation_agreement(reviewer_a, reviewer_b)
    left = completed_by_key(reviewer_a)
    right = completed_by_key(reviewer_b)
    if set(left) != set(right):
        raise ValueError("Both reviewers must complete the same segment keys")
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"Adjudication output already exists: {destination}")
    destination.mkdir(parents=True)
    rows: list[dict[str, object]] = []
    for segment_key in sorted(left):
        if segment_key not in answer_key:
            raise ValueError(f"Unknown segment key: {segment_key}")
        a = left[segment_key]
        b = right[segment_key]
        agreed = (
            a["decision"] == b["decision"]
            and normalized_reasons(a) == normalized_reasons(b)
        )
        rows.append(
            {
                "segment_key": segment_key,
                "reviewer_a_decision": a["decision"],
                "reviewer_b_decision": b["decision"],
                "reviewer_a_reasons": a.get("reasons", ""),
                "reviewer_b_reasons": b.get("reasons", ""),
                "adjudicated_decision": a["decision"] if agreed else "",
                "adjudicated_reasons": a.get("reasons", "") if agreed else "",
                "adjudication_notes": "" if agreed else "REQUIRES_CONSENSUS",
            }
        )
    fields = tuple(rows[0])
    write_csv(destination / "adjudication.csv", fields, rows)
    write_json_atomic(destination / "agreement.json", agreement)
    write_json_atomic(
        destination / "adjudication_manifest.json",
        {
            "schema_version": SCHEMA_VERSION,
            "annotation_set_id": annotation_set_id,
            "annotation_count": len(rows),
            "unresolved_count": sum(
                not row["adjudicated_decision"] for row in rows
            ),
            "agreement_file": "agreement.json",
        },
    )
    return destination


def import_context_annotation_file(
    reviewer_path: str | Path,
    answer_key_path: str | Path,
    output_dir: str | Path,
    *,
    annotation_set_id: str,
    reviewer_id: str,
) -> Path:
    """Validate and freeze one completed blinded reviewer file."""
    source = Path(reviewer_path)
    answer_path = Path(answer_key_path)
    rows = read_csv(source)
    if not rows:
        raise ValueError("The reviewer file is empty")
    unexpected_fields = sorted(set(rows[0]) - set(REVIEW_FIELDS))
    missing_fields = sorted(set(REVIEW_FIELDS) - set(rows[0]))
    if unexpected_fields or missing_fields:
        raise ValueError(
            "Reviewer columns do not match the blinded form: "
            f"missing={missing_fields}, unexpected={unexpected_fields}"
        )
    completed = completed_by_key(rows)
    if len(completed) != len(rows):
        raise ValueError("The reviewer file contains duplicate segment keys")
    answer_key = {
        row["segment_key"]: row for row in read_csv(answer_path)
    }
    if set(completed) != set(answer_key):
        missing = sorted(set(answer_key) - set(completed))
        unexpected = sorted(set(completed) - set(answer_key))
        raise ValueError(
            "Reviewer coverage does not match the answer key: "
            f"missing={len(missing)}, unexpected={len(unexpected)}"
        )
    for segment_key, row in completed.items():
        if row.get("sample_id", "") != answer_key[segment_key].get("sample_id", ""):
            raise ValueError(f"Sample ID mismatch for {segment_key}")
        reasons = normalized_reasons(row)
        invalid = sorted(set(reasons) - ANNOTATION_REASONS)
        if invalid:
            raise ValueError(
                f"Invalid annotation reasons for {segment_key}: {', '.join(invalid)}"
            )
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"Imported annotation output exists: {destination}")
    destination.mkdir(parents=True)
    imported_path = destination / "annotations.csv"
    write_csv(imported_path, REVIEW_FIELDS, completed.values())
    write_json_atomic(
        destination / "import_manifest.json",
        {
            "schema_version": SCHEMA_VERSION,
            "annotation_set_id": annotation_set_id,
            "reviewer_id": reviewer_id,
            "annotation_count": len(completed),
            "source_sha256": file_hash(source),
            "answer_key_sha256": file_hash(answer_path),
            "imported_sha256": file_hash(imported_path),
            "validation": {
                "complete_coverage": True,
                "unique_segment_keys": True,
                "blinded_columns_only": True,
                "valid_decisions_reasons_and_confidence": True,
            },
        },
    )
    return destination


def attach_adjudicated_annotations(
    traces: Iterable[AuditTrace],
    adjudication_path: str | Path,
    answer_key_path: str | Path,
    *,
    annotation_set_id: str,
) -> list[AuditTrace]:
    answer_key = {row["segment_key"]: row for row in read_csv(Path(answer_key_path))}
    annotations_by_trace: dict[str, list[ReferenceAnnotation]] = {}
    for row in read_csv(Path(adjudication_path)):
        decision = row.get("adjudicated_decision", "").strip().lower()
        if decision not in VALID_DECISIONS:
            raise ValueError(
                f"Unresolved or invalid adjudication for {row.get('segment_key')}"
            )
        key = answer_key.get(row["segment_key"])
        if key is None:
            raise ValueError(f"Unknown adjudicated segment key: {row['segment_key']}")
        reasons = tuple(
            item.strip()
            for item in row.get("adjudicated_reasons", "").split(";")
            if item.strip()
        )
        invalid = sorted(set(reasons) - ANNOTATION_REASONS)
        if invalid:
            raise ValueError("Invalid adjudication reasons: " + ", ".join(invalid))
        annotations_by_trace.setdefault(key["trace_id"], []).append(
            ReferenceAnnotation(
                segment_id=key["segment_id"],
                annotator_id="adjudicated-consensus",
                decision=decision,
                reasons=reasons,
                annotation_set_id=annotation_set_id,
                adjudicated=True,
            )
        )
    result = []
    for trace in traces:
        annotations = tuple(annotations_by_trace.get(trace.trace_id, ()))
        result.append(replace(trace, reference_annotations=annotations))
    return result


def load_bundle(bundle: Path) -> tuple[list[AuditTrace], dict]:
    with zipfile.ZipFile(bundle) as archive:
        manifest = json.loads(archive.read("study_manifest.json").decode("utf-8"))
        traces = [
            trace_from_dict(json.loads(line))
            for line in archive.read("traces/invocations.jsonl")
            .decode("utf-8")
            .splitlines()
            if line.strip()
        ]
    return traces, manifest


def completed_by_key(rows: Iterable[dict[str, str]]) -> dict[str, dict[str, str]]:
    result = {}
    for row in rows:
        segment_key = row.get("segment_key", "").strip()
        decision = row.get("decision", "").strip().lower()
        if not segment_key or decision not in VALID_DECISIONS:
            raise ValueError(f"Incomplete or invalid annotation row: {segment_key}")
        confidence = row.get("confidence_1_to_5", "").strip()
        if confidence not in {"1", "2", "3", "4", "5"}:
            raise ValueError(f"Invalid confidence for {segment_key}: {confidence}")
        result[segment_key] = {**row, "decision": decision}
    return result


def normalized_reasons(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            item.strip()
            for item in row.get("reasons", "").split(";")
            if item.strip()
        )
    )


def opaque_id(namespace: str, value: str) -> str:
    digest = hashlib.sha256(f"{namespace}:{value}".encode("utf-8")).hexdigest()
    return "blind-" + digest[:16]


def user_prompt(trace: AuditTrace) -> str:
    return next(
        (
            message.content
            for message in reversed(trace.messages)
            if message.role in {"user", "human"}
        ),
        "",
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path,
    fields: tuple[str, ...],
    rows: Iterable[dict[str, object]],
) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)
