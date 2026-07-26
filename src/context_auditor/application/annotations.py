"""Deterministic, condition-blind human review package export."""

from __future__ import annotations

import csv
import hashlib
import json
import random
import zipfile
from collections import defaultdict
from pathlib import Path

from context_auditor.adapters.storage.jsonl import trace_from_dict
from context_auditor.adapters.storage.runs import file_hash
from context_auditor.adapters.storage.serialization import write_json_atomic
from context_auditor.application.study_bundle import validate_study_bundle
from context_auditor.domain.models import AuditTrace


def export_blind_review_package(
    bundle_path: str | Path,
    output_dir: str | Path,
    *,
    seed: int = 20260726,
    samples_per_stratum: int = 2,
) -> Path:
    bundle = Path(bundle_path)
    validate_study_bundle(bundle)
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"Annotation output already exists: {destination}")
    traces, study_manifest = load_bundle_traces(bundle)
    selected = select_stratified_traces(
        traces,
        seed=seed,
        samples_per_stratum=samples_per_stratum,
    )
    destination.mkdir(parents=True)
    reviewer_rows = []
    answer_rows = []
    by_stratum: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for trace in selected:
        sample_id = blind_sample_id(trace, seed)
        reviewer_row = {
            "sample_id": sample_id,
            "prompt": user_prompt(trace),
            "response": trace.task_output or "",
            "correctness_0_or_1": "",
            "response_relevance_1_to_5": "",
            "notes": "",
        }
        reviewer_rows.append(reviewer_row)
        by_stratum[
            (trace.framework, trace.workflow_family, trace.configuration)
        ].append(reviewer_row)
        answer_rows.append(
            {
                "sample_id": sample_id,
                "task_id": trace.task_id,
                "framework": trace.framework,
                "workflow_family": trace.workflow_family,
                "configuration": trace.configuration,
                "repetition_id": trace.repetition_id,
                "expected_answer": trace.expected_answer or "",
                "automatic_success": trace.task_success,
                "automatic_score": trace.scoring.score if trace.scoring else "",
            }
        )
    second_reviewer_rows = [
        sorted(rows, key=lambda row: row["sample_id"])[0]
        for _, rows in sorted(by_stratum.items())
    ]
    write_csv(
        destination / "reviewer_a.csv",
        (
            "sample_id",
            "prompt",
            "response",
            "correctness_0_or_1",
            "response_relevance_1_to_5",
            "notes",
        ),
        reviewer_rows,
    )
    write_csv(
        destination / "reviewer_b.csv",
        (
            "sample_id",
            "prompt",
            "response",
            "correctness_0_or_1",
            "response_relevance_1_to_5",
            "notes",
        ),
        second_reviewer_rows,
    )
    write_csv(
        destination / "answer_key.csv",
        (
            "sample_id",
            "task_id",
            "framework",
            "workflow_family",
            "configuration",
            "repetition_id",
            "expected_answer",
            "automatic_success",
            "automatic_score",
        ),
        answer_rows,
    )
    manifest = {
        "schema_version": "1.1.0",
        "source_study_id": study_manifest["study_id"],
        "source_bundle_sha256": file_hash(bundle),
        "selection_seed": seed,
        "selection_cohort": "primary",
        "stratification": ["framework", "workflow_family", "configuration"],
        "stratum_count": len(by_stratum),
        "samples_per_stratum": samples_per_stratum,
        "reviewer_a_count": len(reviewer_rows),
        "reviewer_b_count": len(second_reviewer_rows),
        "blinding": {
            "reviewer_files_hide": [
                "task_id",
                "framework",
                "workflow_family",
                "configuration",
                "expected_answer",
                "automatic_score",
            ],
            "answer_key_is_not_for_reviewers": True,
        },
    }
    write_json_atomic(destination / "annotation_manifest.json", manifest)
    return destination


def load_bundle_traces(bundle: Path) -> tuple[list[AuditTrace], dict]:
    with zipfile.ZipFile(bundle) as archive:
        manifest = json.loads(archive.read("study_manifest.json").decode("utf-8"))
        lines = archive.read("traces/invocations.jsonl").decode("utf-8").splitlines()
    return (
        [trace_from_dict(json.loads(line)) for line in lines if line.strip()],
        manifest,
    )


def select_stratified_traces(
    traces: list[AuditTrace],
    *,
    seed: int,
    samples_per_stratum: int,
) -> list[AuditTrace]:
    strata: dict[tuple[str, str, str], list[AuditTrace]] = defaultdict(list)
    for trace in traces:
        if trace.analysis_cohort != "primary" or trace.task_success is None:
            continue
        strata[(trace.framework, trace.workflow_family, trace.configuration)].append(
            trace
        )
    if not strata:
        raise ValueError("The study bundle has no final primary-cohort traces")
    generator = random.Random(seed)
    selected: list[AuditTrace] = []
    for key, candidates in sorted(strata.items()):
        ordered = sorted(
            candidates,
            key=lambda trace: (
                trace.task_id,
                trace.repetition_id,
                trace.trace_id,
            ),
        )
        if len(ordered) < samples_per_stratum:
            raise ValueError(
                f"Stratum {key!r} has {len(ordered)} traces; "
                f"{samples_per_stratum} are required"
            )
        selected.extend(generator.sample(ordered, samples_per_stratum))
    return sorted(
        selected,
        key=lambda trace: (
            trace.framework,
            trace.workflow_family,
            trace.configuration,
            trace.task_id,
            trace.repetition_id,
        ),
    )


def blind_sample_id(trace: AuditTrace, seed: int) -> str:
    value = f"{seed}:{trace.trace_id}".encode("utf-8")
    return "sample-" + hashlib.sha256(value).hexdigest()[:12]


def user_prompt(trace: AuditTrace) -> str:
    return next(
        (
            message.content
            for message in reversed(trace.messages)
            if message.role in {"user", "human"}
        ),
        "",
    )


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)
