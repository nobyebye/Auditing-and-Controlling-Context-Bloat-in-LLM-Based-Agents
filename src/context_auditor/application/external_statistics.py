"""Prespecified Study B statistics using independent human annotations."""

from __future__ import annotations

from collections import defaultdict
import math
import random
from statistics import mean
from typing import Callable

from context_auditor.application.evaluation import (
    BOOTSTRAP_SAMPLES,
    BOOTSTRAP_SEED,
    bland_altman,
    linear_calibration,
    spearman_correlation,
)
from context_auditor.domain.models import AuditTrace, TextSegment

POLICIES = ("primary", "uncertain_as_keep", "uncertain_as_remove")
PROTECTED_SOURCES = frozenset({"system", "user", "tool_schema"})


def build_study_b_statistics(traces: list[AuditTrace]) -> dict:
    final = [
        trace
        for trace in traces
        if trace.evidence_tier == "natural" and trace.task_success is not None
    ]
    by_policy = {
        policy: {
            "rq1_detection_and_localization": evaluate_rq1(final, policy),
            "rq2_human_measurement_validity": evaluate_rq2(final, policy),
            "rq3_source_patterns": evaluate_rq3(final, policy),
        }
        for policy in POLICIES
    }
    return {
        "analysis_unit": "task_id",
        "framework_handling": (
            "Both framework traces and all segments are retained inside each "
            "task_id bootstrap cluster."
        ),
        "segment_boundary_rule": (
            "Segment IDs and boundaries are frozen before annotation; "
            "framework traces are never post-hoc aligned."
        ),
        "uncertain_policy": {
            "primary": "exclude uncertain segments",
            "uncertain_as_keep": "treat uncertain as keep/non-bloat",
            "uncertain_as_remove": "treat uncertain as remove/bloat",
        },
        "by_policy": by_policy,
    }


def evaluate_rq1(traces: list[AuditTrace], policy: str) -> dict:
    context_rows = []
    by_task: dict[str, list[tuple[int, int, int, int]]] = defaultdict(list)
    task_ious: dict[str, list[float]] = defaultdict(list)
    for trace in traces:
        eligible = annotated_segments(trace, policy)
        if not eligible:
            continue
        truth = {
            segment.segment_id
            for segment, decision in eligible
            if decision == 1
        }
        detected = {
            segment.segment_id
            for segment, _decision in eligible
            if trace.detected_labels.get(segment.segment_id)
        }
        human_positive = bool(truth)
        detector_positive = bool(detected)
        context_rows.append(
            {
                "task_id": trace.task_id,
                "human_positive": human_positive,
                "detector_positive": detector_positive,
            }
        )
        counts = binary_counts(
            truth,
            detected,
            {segment.segment_id for segment, _ in eligible},
        )
        by_task[trace.task_id].append(
            (
                counts["true_positive"],
                counts["false_positive"],
                counts["false_negative"],
                counts["true_negative"],
            )
        )
        union = truth | detected
        if union:
            tokens = {segment.segment_id: segment.token_count for segment, _ in eligible}
            intersection_tokens = sum(tokens[item] for item in truth & detected)
            union_tokens = sum(tokens[item] for item in union)
            task_ious[trace.task_id].append(
                intersection_tokens / union_tokens if union_tokens else 0.0
            )
    context = context_confusion(context_rows)
    task_metrics = []
    for task_id, rows in by_task.items():
        tp = sum(row[0] for row in rows)
        fp = sum(row[1] for row in rows)
        fn = sum(row[2] for row in rows)
        tn = sum(row[3] for row in rows)
        task_metrics.append({"task_id": task_id, **metrics_from_counts(tp, fp, fn, tn)})
    eligible_f1 = [
        row["f1"]
        for row in task_metrics
        if row["true_positive"] + row["false_positive"] + row["false_negative"] > 0
    ]
    human_negative_contexts = [
        row for row in context_rows if not row["human_positive"]
    ]
    false_positive_rate = (
        sum(row["detector_positive"] for row in human_negative_contexts)
        / len(human_negative_contexts)
        if human_negative_contexts
        else None
    )
    return {
        "context_level": {
            **context,
            "ci95": {
                name: task_cluster_interval(
                    context_rows,
                    lambda rows, metric=name: context_confusion(rows)[metric],
                )
                for name in ("sensitivity", "specificity", "precision", "f1")
            },
        },
        "task_macro_segment": {
            "task_count": len(task_metrics),
            "precision": macro_defined(task_metrics, "precision", "predicted_positive"),
            "recall": macro_defined(task_metrics, "recall", "reference_positive"),
            "f1": mean(eligible_f1) if eligible_f1 else None,
            "f1_ci95": bootstrap_task_metric(task_metrics, "f1", require_union=True),
        },
        "token_weighted_localization_iou": (
            mean(mean(values) for values in task_ious.values())
            if task_ious
            else None
        ),
        "token_weighted_localization_iou_ci95": bootstrap_group_means(task_ious),
        "false_positive_rate_in_human_negative_contexts": false_positive_rate,
        "excluded_context_count": len(traces) - len(context_rows),
    }


def evaluate_rq2(traces: list[AuditTrace], policy: str) -> dict:
    rows = []
    for trace in traces:
        eligible = annotated_segments(trace, policy)
        if not eligible:
            continue
        denominator = sum(segment.token_count for segment, _ in eligible)
        human_tokens = sum(
            segment.token_count
            for segment, decision in eligible
            if decision == 1
        )
        detected_tokens = sum(
            segment.token_count
            for segment, _decision in eligible
            if trace.detected_labels.get(segment.segment_id)
        )
        rows.append(
            {
                "task_id": trace.task_id,
                "human_ratio": human_tokens / denominator if denominator else 0.0,
                "detector_ratio": detected_tokens / denominator if denominator else 0.0,
            }
        )
    human = [row["human_ratio"] for row in rows]
    detector = [row["detector_ratio"] for row in rows]
    differences = [d - h for h, d in zip(human, detector)]
    return {
        "context_count": len(rows),
        "task_count": len({row["task_id"] for row in rows}),
        "spearman_rho": spearman_correlation(human, detector),
        "spearman_rho_ci95": task_cluster_interval(
            rows,
            lambda sampled: spearman_correlation(
                [row["human_ratio"] for row in sampled],
                [row["detector_ratio"] for row in sampled],
            ),
        ),
        "mean_absolute_error": (
            mean(abs(row["human_ratio"] - row["detector_ratio"]) for row in rows)
            if rows
            else None
        ),
        "calibration": linear_calibration(detector, human),
        "bland_altman": bland_altman(differences),
        "evidence_scope": "agreement_with_human_reference_labels_only",
        "counterfactual_evidence_combined": False,
    }


def evaluate_rq3(traces: list[AuditTrace], policy: str) -> dict:
    task_source: dict[str, dict[str, list[tuple[int, int]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for trace in traces:
        grouped: dict[str, list[tuple[TextSegment, int]]] = defaultdict(list)
        for segment, decision in annotated_segments(trace, policy):
            grouped[segment.source_type].append((segment, decision))
        for source, values in grouped.items():
            denominator = sum(segment.token_count for segment, _ in values)
            numerator = sum(
                segment.token_count
                for segment, decision in values
                if decision == 1
            )
            task_source[trace.task_id][source].append((numerator, denominator))
    counts: dict[str, dict[str, tuple[int, int]]] = defaultdict(dict)
    for task_id, sources in task_source.items():
        for source, framework_values in sources.items():
            numerator = sum(item[0] for item in framework_values)
            denominator = sum(item[1] for item in framework_values)
            if denominator:
                counts[source][task_id] = (numerator, denominator)
    ranking = []
    for source, values in counts.items():
        point_estimate = aggregate_token_ratio(values.values())
        ranking.append(
            {
                "source": source,
                "task_count": len(values),
                "human_reference_bloat_token_ratio": point_estimate,
                "ci95": source_ratio_interval(values),
            }
        )
    ranking.sort(
        key=lambda item: (
            -item["human_reference_bloat_token_ratio"],
            item["source"],
        )
    )
    pairwise = []
    for index, left in enumerate(ranking):
        for right in ranking[index + 1 :]:
            ci = source_difference_interval(
                counts[left["source"]],
                counts[right["source"]],
            )
            pairwise.append(
                {
                    "left": left["source"],
                    "right": right["source"],
                    "ratio_difference": (
                        left["human_reference_bloat_token_ratio"]
                        - right["human_reference_bloat_token_ratio"]
                    ),
                    "task_cluster_bootstrap_difference_ci95": ci,
                    "interpretation": (
                        "indistinguishable_at_prespecified_confidence_level"
                        if ci and ci[0] <= 0 <= ci[1]
                        else "directionally_distinguishable"
                    ),
                }
            )
    return {
        "ranking_statistic": (
            "After combining both frameworks within task: total adjudicated "
            "REMOVE tokens for a source divided by total eligible annotated "
            "tokens for that source across task clusters"
        ),
        "ranking": ranking,
        "pairwise_differences": pairwise,
        "absent_source_handling": "NA",
        "causal_claim": False,
        "workflow_source_confounding": True,
    }


def annotated_segments(
    trace: AuditTrace,
    policy: str,
) -> list[tuple[TextSegment, int]]:
    annotations = {
        item.segment_id: item
        for item in trace.reference_annotations
        if item.adjudicated
    }
    result = []
    for segment in trace.segments:
        if (
            segment.source_type in PROTECTED_SOURCES
            or segment.container_type
            in {"system_instruction", "tool_definition", "response_format"}
            or not segment.text.strip()
            or segment.segment_id not in annotations
        ):
            continue
        decision = annotations[segment.segment_id].decision
        if decision == "uncertain" and policy == "primary":
            continue
        result.append(
            (
                segment,
                int(
                    decision == "remove"
                    or (
                        decision == "uncertain"
                        and policy == "uncertain_as_remove"
                    )
                ),
            )
        )
    return result


def binary_counts(
    truth: set[str],
    detected: set[str],
    eligible: set[str],
) -> dict[str, int]:
    return {
        "true_positive": len(truth & detected),
        "false_positive": len(detected - truth),
        "false_negative": len(truth - detected),
        "true_negative": len(eligible - truth - detected),
    }


def metrics_from_counts(tp: int, fp: int, fn: int, tn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    specificity = tn / (tn + fp) if tn + fp else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return {
        "true_positive": tp,
        "true_negative": tn,
        "false_positive": fp,
        "false_negative": fn,
        "reference_positive": tp + fn,
        "predicted_positive": tp + fp,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": f1,
    }


def context_confusion(rows: list[dict]) -> dict:
    tp = sum(row["human_positive"] and row["detector_positive"] for row in rows)
    tn = sum(not row["human_positive"] and not row["detector_positive"] for row in rows)
    fp = sum(not row["human_positive"] and row["detector_positive"] for row in rows)
    fn = sum(row["human_positive"] and not row["detector_positive"] for row in rows)
    metrics = metrics_from_counts(tp, fp, fn, tn)
    return {
        "context_count": len(rows),
        **metrics,
        "sensitivity": metrics["recall"],
    }


def macro_defined(rows: list[dict], metric: str, denominator: str) -> float | None:
    values = [row[metric] for row in rows if row[denominator] > 0]
    return mean(values) if values else None


def bootstrap_task_metric(
    rows: list[dict],
    metric: str,
    *,
    require_union: bool = False,
) -> list[float] | None:
    filtered = [
        row[metric]
        for row in rows
        if row[metric] is not None
        and (
            not require_union
            or row["reference_positive"] + row["predicted_positive"] > 0
        )
    ]
    return simple_bootstrap_interval(filtered)


def bootstrap_group_means(
    values: dict[str, list[float]],
) -> list[float] | None:
    return simple_bootstrap_interval(
        [mean(items) for items in values.values() if items]
    )


def task_cluster_interval(
    rows: list[dict],
    statistic: Callable[[list[dict]], float | None],
) -> list[float] | None:
    by_task: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_task[row["task_id"]].append(row)
    task_ids = sorted(by_task)
    if not task_ids:
        return None
    generator = random.Random(BOOTSTRAP_SEED)
    estimates = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sampled = []
        for _position in task_ids:
            sampled.extend(by_task[generator.choice(task_ids)])
        value = statistic(sampled)
        if value is not None:
            estimates.append(float(value))
    return percentile_bounds(estimates)


def simple_bootstrap_interval(values: list[float]) -> list[float] | None:
    if not values:
        return None
    generator = random.Random(BOOTSTRAP_SEED)
    estimates = [
        mean(generator.choice(values) for _ in values)
        for _ in range(BOOTSTRAP_SAMPLES)
    ]
    return percentile_bounds(estimates)


def source_difference_interval(
    left: dict[str, tuple[int, int]],
    right: dict[str, tuple[int, int]],
) -> list[float] | None:
    task_ids = sorted(set(left) | set(right))
    if not left or not right:
        return None
    generator = random.Random(BOOTSTRAP_SEED)
    estimates = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sampled = [generator.choice(task_ids) for _ in task_ids]
        left_values = [left[task] for task in sampled if task in left]
        right_values = [right[task] for task in sampled if task in right]
        if left_values and right_values:
            estimates.append(
                aggregate_token_ratio(left_values)
                - aggregate_token_ratio(right_values)
            )
    return percentile_bounds(estimates)


def source_ratio_interval(
    values: dict[str, tuple[int, int]],
) -> list[float] | None:
    task_ids = sorted(values)
    if not task_ids:
        return None
    generator = random.Random(BOOTSTRAP_SEED)
    estimates = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sampled = [
            values[generator.choice(task_ids)]
            for _task_id in task_ids
        ]
        estimates.append(aggregate_token_ratio(sampled))
    return percentile_bounds(estimates)


def aggregate_token_ratio(values) -> float:
    materialized = list(values)
    numerator = sum(item[0] for item in materialized)
    denominator = sum(item[1] for item in materialized)
    return numerator / denominator if denominator else 0.0


def percentile_bounds(values: list[float]) -> list[float] | None:
    if not values:
        return None
    ordered = sorted(values)
    return [
        ordered[math.floor((len(ordered) - 1) * 0.025)],
        ordered[math.ceil((len(ordered) - 1) * 0.975)],
    ]
