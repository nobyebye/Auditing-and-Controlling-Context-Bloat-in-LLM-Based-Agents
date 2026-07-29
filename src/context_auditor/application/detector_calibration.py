"""Deterministic, calibration-only selection of heuristic thresholds."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
from statistics import mean
from typing import Iterable

from context_auditor.adapters.storage.runs import file_hash
from context_auditor.adapters.storage.serialization import write_json_atomic
from context_auditor.application.annotation_workbooks import (
    read_annotation_workbooks,
)
from context_auditor.application.external_annotations import (
    annotation_input_hash,
    read_csv,
    write_csv,
)
from context_auditor.application.localization import (
    findings_by_segment,
    localize_segments,
)
from context_auditor.domain.models import SCHEMA_VERSION, TextSegment

DEFAULT_THRESHOLDS = {
    "near_duplicate_threshold": 0.80,
    "relevance_threshold": 0.05,
    "verbose_tool_token_threshold": 80,
    "source_dominance_threshold": 0.65,
}
SIGNALS = {
    "near_duplicate": {
        "parameter": "near_duplicate_threshold",
        "reason": "near_duplicate",
        "candidates": tuple(round(0.60 + 0.05 * index, 2) for index in range(8)),
        "direction": "similarity >= threshold",
        "conservative": "higher",
    },
    "low_query_relevance": {
        "parameter": "relevance_threshold",
        "reason": "low_query_relevance",
        "candidates": (0.00, 0.025, 0.05, 0.075, 0.10, 0.15, 0.20),
        "direction": "relevance <= threshold",
        "conservative": "lower",
    },
    "verbose_tool_output": {
        "parameter": "verbose_tool_token_threshold",
        "reason": "verbose_tool_output",
        "candidates": (40, 60, 80, 100, 120, 160),
        "direction": "token_count >= threshold",
        "conservative": "higher",
    },
}
FORBIDDEN_KEYS = frozenset(
    {
        "answer",
        "answer_key",
        "expected_answer",
        "task_answer",
        "task_output",
        "model_output",
        "task_success",
        "automatic_score",
        "score",
        "scoring",
        "detected_label",
        "detected_labels",
        "detector_prediction",
        "detector_predictions",
    }
)
LINKAGE_FIELDS = frozenset(
    {
        "sample_id",
        "segment_key",
        "trace_id",
        "task_id",
        "framework",
        "workflow_family",
        "segment_id",
        "source_type",
        "token_count",
    }
)


def calibrate_detector(
    context_bundle_path: str | Path,
    reviewer_a_path: str | Path,
    reviewer_b_path: str | Path,
    adjudication_path: str | Path,
    annotation_linkage_path: str | Path,
    output_dir: str | Path,
    *,
    annotation_set_id: str,
) -> Path:
    """Select thresholds without reading held-out or task-outcome evidence."""
    sources = {
        "context_bundle": Path(context_bundle_path),
        "reviewer_a": Path(reviewer_a_path),
        "reviewer_b": Path(reviewer_b_path),
        "adjudication": Path(adjudication_path),
        "annotation_linkage": Path(annotation_linkage_path),
    }
    for name, path in sources.items():
        if not path.exists():
            raise FileNotFoundError(f"Calibration input is missing ({name}): {path}")
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"Calibration output already exists: {destination}")

    contexts = _load_context_bundle(sources["context_bundle"])
    linkage_rows = read_csv(sources["annotation_linkage"])
    _validate_linkage(linkage_rows)
    reviewer_a = read_annotation_workbooks(sources["reviewer_a"])
    reviewer_b = read_annotation_workbooks(sources["reviewer_b"])
    adjudication = read_csv(sources["adjudication"])
    _reject_forbidden(reviewer_a, "reviewer A annotations")
    _reject_forbidden(reviewer_b, "reviewer B annotations")
    _reject_forbidden(adjudication, "adjudication")

    linkage = {row["segment_key"]: row for row in linkage_rows}
    raw_a = _rows_by_key(reviewer_a)
    raw_b = _rows_by_key(reviewer_b)
    consensus = {
        row.get("segment_key", ""): row
        for row in adjudication
        if row.get("segment_key", "")
    }
    expected_keys = set(linkage)
    coverage_complete = (
        set(raw_a) == expected_keys
        and set(raw_b) == expected_keys
        and set(consensus) == expected_keys
    )
    context_by_trace = {item["trace_id"]: item for item in contexts}
    if {row["trace_id"] for row in linkage_rows} - set(context_by_trace):
        raise ValueError("Annotation linkage refers to missing calibration contexts")
    segment_by_trace = {
        item["trace_id"]: {
            segment["segment_id"]: TextSegment(**segment)
            for segment in item["segments"]
        }
        for item in contexts
    }
    for row in linkage_rows:
        if row["segment_id"] not in segment_by_trace[row["trace_id"]]:
            raise ValueError("Annotation linkage refers to a missing segment")

    destination.mkdir(parents=True)
    selected = dict(DEFAULT_THRESHOLDS)
    audit_rows = []
    selection = {}
    for signal, definition in SIGNALS.items():
        parameter = str(definition["parameter"])
        default = DEFAULT_THRESHOLDS[parameter]
        positives = _positive_count(consensus, str(definition["reason"]))
        fallback_reason = None
        if not coverage_complete:
            fallback_reason = "annotation_coverage_incomplete"
        elif positives == 0:
            fallback_reason = "no_corresponding_adjudicated_remove_positive"

        candidates = []
        if fallback_reason is None:
            for candidate in definition["candidates"]:
                metrics = _evaluate_candidate(
                    contexts,
                    linkage_rows,
                    consensus,
                    signal,
                    candidate,
                )
                candidates.append(
                    {
                        "signal": signal,
                        "parameter": parameter,
                        "candidate": candidate,
                        **metrics,
                    }
                )
            estimable = [
                item
                for item in candidates
                if math.isfinite(float(item["task_macro_f1"]))
                and math.isfinite(float(item["task_macro_precision"]))
            ]
            if not estimable:
                fallback_reason = "metric_not_estimable"
            else:
                chosen = max(
                    estimable,
                    key=lambda item: _candidate_rank(
                        item,
                        default=float(default),
                        conservative=str(definition["conservative"]),
                    ),
                )
                selected[parameter] = chosen["candidate"]
                selection[signal] = {
                    "selected": chosen["candidate"],
                    "selection_reason": "deterministic_prespecified_tie_break",
                    "positive_segment_count": positives,
                    "direction": definition["direction"],
                    "conservative_threshold": definition["conservative"],
                }
        if fallback_reason is not None:
            selected[parameter] = default
            selection[signal] = {
                "selected": default,
                "selection_reason": fallback_reason,
                "positive_segment_count": positives,
                "direction": definition["direction"],
                "conservative_threshold": definition["conservative"],
            }
        for item in candidates:
            audit_rows.append(
                {
                    **item,
                    "selected": str(
                        item["candidate"] == selected[parameter]
                    ).lower(),
                }
            )

    selected_payload = {
        "schema_version": SCHEMA_VERSION,
        "annotation_set_id": annotation_set_id,
        "scope": "calibration_only",
        "thresholds": selected,
        "fixed_rules": {
            "exact_duplicate": (
                "normalized_hash equality; not searched"
            ),
            "source_dominance": "source_ratio >= 0.65; not searched",
            "stale_conflicting": (
                "human-reference error-analysis category only"
            ),
        },
        "selection": selection,
        "uncertain_primary_analysis": "excluded",
        "framework_aggregation": (
            "segments from both frameworks are combined within task_id"
        ),
        "annotation_coverage_complete": coverage_complete,
        "input_sha256": {
            "context_bundle": file_hash(sources["context_bundle"]),
            "reviewer_a": annotation_input_hash(sources["reviewer_a"]),
            "reviewer_b": annotation_input_hash(sources["reviewer_b"]),
            "adjudication": file_hash(sources["adjudication"]),
            "annotation_linkage": file_hash(sources["annotation_linkage"]),
        },
    }
    write_json_atomic(destination / "selected_thresholds.json", selected_payload)
    if audit_rows:
        write_csv(
            destination / "threshold_selection_audit.csv",
            tuple(audit_rows[0]),
            audit_rows,
        )
    else:
        write_csv(
            destination / "threshold_selection_audit.csv",
            (
                "signal",
                "parameter",
                "candidate",
                "task_count",
                "task_macro_precision",
                "task_macro_recall",
                "task_macro_f1",
                "selected",
            ),
            [],
        )
    write_json_atomic(
        destination / "calibration_summary.json",
        {
            **selected_payload,
            "selected_thresholds_sha256": file_hash(
                destination / "selected_thresholds.json"
            ),
            "selection_audit_sha256": file_hash(
                destination / "threshold_selection_audit.csv"
            ),
        },
    )
    return destination


def _load_context_bundle(path: Path) -> list[dict]:
    contexts = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        item = json.loads(line)
        _reject_forbidden(item, f"context bundle line {line_number}")
        if item.get("dataset_split") != "calibration":
            raise ValueError("Detector calibration rejects held-out traces")
        required = {
            "trace_id",
            "task_id",
            "framework",
            "workflow_family",
            "dataset_split",
            "query",
            "segments",
        }
        if not required <= set(item):
            raise ValueError("Calibration context bundle is incomplete")
        contexts.append(item)
    if not contexts:
        raise ValueError("Calibration context bundle is empty")
    return contexts


def _validate_linkage(rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError("Annotation linkage is empty")
    observed = set(rows[0])
    forbidden = observed & FORBIDDEN_KEYS
    if forbidden:
        raise ValueError(
            "Annotation linkage contains forbidden fields: "
            + ", ".join(sorted(forbidden))
        )
    if observed != LINKAGE_FIELDS:
        raise ValueError(
            "Annotation linkage fields are not frozen: "
            f"expected={sorted(LINKAGE_FIELDS)}, observed={sorted(observed)}"
        )
    if len({row["segment_key"] for row in rows}) != len(rows):
        raise ValueError("Annotation linkage contains duplicate segment keys")


def _reject_forbidden(value, location: str) -> None:
    if isinstance(value, dict):
        found = {str(key).lower() for key in value} & FORBIDDEN_KEYS
        if found:
            raise ValueError(
                f"{location} contains forbidden calibration fields: "
                + ", ".join(sorted(found))
            )
        for item in value.values():
            _reject_forbidden(item, location)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_forbidden(item, location)


def _rows_by_key(rows: Iterable[dict[str, str]]) -> dict[str, dict[str, str]]:
    result = {}
    for row in rows:
        key = row.get("segment_key", "")
        if not key or key in result:
            raise ValueError("Raw annotations require unique segment keys")
        result[key] = row
    return result


def _positive_count(consensus: dict[str, dict[str, str]], reason: str) -> int:
    return sum(
        row.get("adjudicated_decision", "").strip().lower() == "remove"
        and reason in _reasons(row)
        for row in consensus.values()
    )


def _reasons(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in row.get("adjudicated_reasons", "").split(";")
        if item.strip()
    )


def _evaluate_candidate(
    contexts: list[dict],
    linkage_rows: list[dict[str, str]],
    consensus: dict[str, dict[str, str]],
    signal: str,
    candidate: float | int,
) -> dict:
    predictions: dict[tuple[str, str], set[str]] = {}
    for context in contexts:
        segments = tuple(TextSegment(**item) for item in context["segments"])
        kwargs = {
            "near_duplicate_threshold": DEFAULT_THRESHOLDS[
                "near_duplicate_threshold"
            ],
            "relevance_threshold": DEFAULT_THRESHOLDS["relevance_threshold"],
            "verbose_tool_token_threshold": DEFAULT_THRESHOLDS[
                "verbose_tool_token_threshold"
            ],
        }
        if signal == "near_duplicate":
            kwargs["near_duplicate_threshold"] = float(candidate)
        elif signal == "low_query_relevance":
            kwargs["relevance_threshold"] = float(candidate)
        elif signal == "verbose_tool_output":
            kwargs["verbose_tool_token_threshold"] = int(candidate)
        labels = findings_by_segment(
            localize_segments(
                segments,
                str(context["query"]),
                **kwargs,
            )
        )
        predictions[(context["trace_id"], signal)] = {
            segment_id
            for segment_id, values in labels.items()
            if signal in values
        }

    reason = str(SIGNALS[signal]["reason"])
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for linkage in linkage_rows:
        annotation = consensus.get(linkage["segment_key"], {})
        decision = annotation.get("adjudicated_decision", "").strip().lower()
        if decision == "uncertain" or decision not in {"keep", "remove"}:
            continue
        positive = decision == "remove" and reason in _reasons(annotation)
        predicted = linkage["segment_id"] in predictions[
            (linkage["trace_id"], signal)
        ]
        task = linkage["task_id"]
        if positive and predicted:
            counts[task][0] += 1
        elif not positive and predicted:
            counts[task][1] += 1
        elif positive and not predicted:
            counts[task][2] += 1
    task_metrics = []
    for task_id in sorted(counts):
        tp, fp, fn = counts[task_id]
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        task_metrics.append((precision, recall, f1))
    if not task_metrics:
        return {
            "task_count": 0,
            "task_macro_precision": float("nan"),
            "task_macro_recall": float("nan"),
            "task_macro_f1": float("nan"),
        }
    return {
        "task_count": len(task_metrics),
        "task_macro_precision": mean(item[0] for item in task_metrics),
        "task_macro_recall": mean(item[1] for item in task_metrics),
        "task_macro_f1": mean(item[2] for item in task_metrics),
    }


def _candidate_rank(
    item: dict,
    *,
    default: float,
    conservative: str,
) -> tuple[float, float, float, float, float]:
    value = float(item["candidate"])
    conservative_rank = value if conservative == "higher" else -value
    return (
        float(item["task_macro_f1"]),
        float(item["task_macro_precision"]),
        -abs(value - default),
        conservative_rank,
        -value,
    )


def calibration_result_hash(path: str | Path) -> str:
    """Stable helper used by addendum builders and tests."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def apply_selected_thresholds(
    selected_thresholds_path: str | Path,
    heldout_config_paths: Iterable[str | Path],
    audit_output_path: str | Path,
) -> Path:
    """Apply frozen calibration results only to held-out configs."""
    selected_path = Path(selected_thresholds_path)
    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    if selected.get("scope") != "calibration_only":
        raise ValueError("Selected thresholds lack calibration-only scope")
    thresholds = selected.get("thresholds", {})
    if set(thresholds) != set(DEFAULT_THRESHOLDS):
        raise ValueError("Selected threshold fields are incomplete or unexpected")
    if float(thresholds["source_dominance_threshold"]) != 0.65:
        raise ValueError("Source dominance must remain fixed at 0.65")
    targets = [Path(item) for item in heldout_config_paths]
    if not targets:
        raise ValueError("At least one held-out config is required")
    audit_path = Path(audit_output_path)
    if audit_path.exists():
        raise FileExistsError(f"Threshold application audit exists: {audit_path}")
    prepared = []
    for target in targets:
        data = json.loads(target.read_text(encoding="utf-8"))
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"Held-out config uses the wrong schema: {target}")
        if data.get("dataset_split") != "test":
            raise ValueError(f"Thresholds may only update test configs: {target}")
        before = file_hash(target)
        updated = {**data, **thresholds}
        prepared.append((target, updated, before))
    rows = []
    for target, updated, before in prepared:
        write_json_atomic(target, updated)
        rows.append(
            {
                "config_path": str(target),
                "before_sha256": before,
                "after_sha256": file_hash(target),
            }
        )
    write_json_atomic(
        audit_path,
        {
            "schema_version": SCHEMA_VERSION,
            "selected_thresholds_sha256": file_hash(selected_path),
            "thresholds": thresholds,
            "configs": rows,
        },
    )
    return audit_path
