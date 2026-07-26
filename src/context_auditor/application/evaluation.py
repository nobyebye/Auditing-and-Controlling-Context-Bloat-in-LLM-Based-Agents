"""Detection, correlation, and paired mitigation evaluation."""

from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean
from typing import Iterable

from context_auditor.domain.models import AuditTrace


def evaluate_detection(traces: Iterable[AuditTrace]) -> dict:
    items = list(traces)
    truth = {
        (trace.trace_id, segment_id, label)
        for trace in items
        for segment_id, labels in trace.ground_truth_labels.items()
        for label in labels
    }
    detected = {
        (trace.trace_id, segment_id, label)
        for trace in items
        for segment_id, labels in trace.detected_labels.items()
        for label in labels
    }
    labels = sorted({item[2] for item in truth | detected})
    by_label = {}
    macro_f1_values: list[float] = []
    for label in labels:
        label_truth = {item for item in truth if item[2] == label}
        label_detected = {item for item in detected if item[2] == label}
        row = classification_counts(label_truth, label_detected)
        by_label[label] = row
        macro_f1_values.append(row["f1"])
    overall = classification_counts(truth, detected)
    truth_segments = {(trace_id, segment_id) for trace_id, segment_id, _ in truth}
    localized_segments = {
        (trace_id, segment_id)
        for trace_id, segment_id, _ in truth & detected
    }
    return {
        "ground_truth_label_count": len(truth),
        "detected_label_count": len(detected),
        "precision": overall["precision"],
        "recall": overall["recall"],
        "f1": overall["f1"],
        "macro_f1": mean(macro_f1_values) if macro_f1_values else None,
        "localization_accuracy": (
            len(localized_segments) / len(truth_segments) if truth_segments else None
        ),
        "confusion": {
            "true_positive": overall["true_positive"],
            "false_positive": overall["false_positive"],
            "false_negative": overall["false_negative"],
        },
        "by_label": by_label,
    }


def classification_counts(truth: set, detected: set) -> dict:
    true_positive = len(truth & detected)
    false_positive = len(detected - truth)
    false_negative = len(truth - detected)
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 0.0
    )
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def evaluate_measurement(traces: Iterable[AuditTrace]) -> dict:
    final = [trace for trace in traces if trace.task_success is not None]
    truth = [
        float(trace.metrics.get("ground_truth_bloat_ratio", 0.0)) for trace in final
    ]
    measured = [
        max(
            float(trace.metrics.get("redundancy_ratio", 0.0)),
            float(trace.metrics.get("near_redundancy_ratio", 0.0)),
            float(trace.metrics.get("detected_bloat_ratio", 0.0)),
        )
        for trace in final
    ]
    return {
        "sample_size": len(final),
        "spearman_rho": spearman_correlation(truth, measured),
        "mean_ground_truth_bloat_ratio": mean(truth) if truth else None,
        "mean_measured_bloat_ratio": mean(measured) if measured else None,
    }


def evaluate_mitigation(
    traces: Iterable[AuditTrace],
    bloated_condition: str = "combined_bloat",
    mitigated_condition: str = "mitigated",
) -> dict:
    final = [trace for trace in traces if trace.task_success is not None]
    keyed: dict[tuple[str, str, int], dict[str, AuditTrace]] = defaultdict(dict)
    for trace in final:
        keyed[(trace.framework, trace.task_id, trace.repetition_id)][
            trace.configuration
        ] = trace
    pairs = [
        (conditions[bloated_condition], conditions[mitigated_condition])
        for conditions in keyed.values()
        if bloated_condition in conditions and mitigated_condition in conditions
    ]
    token_reductions = [
        float(before.metrics.get("total_tokens", 0))
        - float(after.metrics.get("total_tokens", 0))
        for before, after in pairs
    ]
    token_reduction_ratios = [
        reduction / float(before.metrics.get("total_tokens", 1))
        for reduction, (before, _) in zip(token_reductions, pairs)
        if float(before.metrics.get("total_tokens", 0)) > 0
    ]
    success_differences = [
        float(bool(after.task_success)) - float(bool(before.task_success))
        for before, after in pairs
    ]
    return {
        "pair_count": len(pairs),
        "mean_token_reduction": mean(token_reductions) if token_reductions else None,
        "mean_token_reduction_ratio": (
            mean(token_reduction_ratios) if token_reduction_ratios else None
        ),
        "mean_task_success_difference": (
            mean(success_differences) if success_differences else None
        ),
        "task_success_difference_ci95": percentile_interval(success_differences),
        "token_reduction_ci95": percentile_interval(token_reductions),
    }


def spearman_correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_rank = ranks(left)
    right_rank = ranks(right)
    left_mean = mean(left_rank)
    right_mean = mean(right_rank)
    numerator = sum(
        (a - left_mean) * (b - right_mean)
        for a, b in zip(left_rank, right_rank)
    )
    denominator = math.sqrt(
        sum((value - left_mean) ** 2 for value in left_rank)
        * sum((value - right_mean) ** 2 for value in right_rank)
    )
    return numerator / denominator if denominator else 0.0


def ranks(values: list[float]) -> list[float]:
    sorted_indices = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    position = 0
    while position < len(values):
        end = position
        while (
            end + 1 < len(values)
            and values[sorted_indices[end + 1]] == values[sorted_indices[position]]
        ):
            end += 1
        rank = (position + end + 2) / 2
        for index in sorted_indices[position : end + 1]:
            result[index] = rank
        position = end + 1
    return result


def percentile_interval(values: list[float]) -> list[float] | None:
    if not values:
        return None
    ordered = sorted(values)
    low = ordered[max(0, math.floor((len(ordered) - 1) * 0.025))]
    high = ordered[min(len(ordered) - 1, math.ceil((len(ordered) - 1) * 0.975))]
    return [low, high]
