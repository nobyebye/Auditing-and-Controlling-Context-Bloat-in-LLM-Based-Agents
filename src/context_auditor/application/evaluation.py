"""Detection, correlation, and paired mitigation evaluation."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from statistics import mean
from typing import Callable, Iterable

from context_auditor.domain.models import AuditTrace

BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_SEED = 20260726


def evaluate_detection(traces: Iterable[AuditTrace]) -> dict:
    items = list(traces)
    result = _detection_metrics(items)
    reference_type = (
        "human_reference"
        if any(trace.reference_annotations for trace in items)
        else "injected_perturbation"
    )
    by_task: dict[str, list[AuditTrace]] = defaultdict(list)
    for trace in items:
        by_task[trace.task_id].append(trace)
    task_rows = [_detection_metrics(group) for group in by_task.values()]
    task_macro_f1 = [
        float(row["macro_f1"])
        for row in task_rows
        if row["macro_f1"] is not None
    ]
    task_binary_f1 = [
        float(row["binary"]["f1"])
        for row in task_rows
        if row["binary"]["f1"] is not None
    ]
    task_localization = [
        float(row["localization_accuracy"])
        for row in task_rows
        if row["localization_accuracy"] is not None
    ]
    return {
        **result,
        "reference_type": reference_type,
        "task_sample_size": len(by_task),
        "task_macro_binary_f1": (
            mean(task_binary_f1) if task_binary_f1 else None
        ),
        "task_macro_binary_f1_ci95": bootstrap_mean_interval(task_binary_f1),
        "macro_f1_ci95": bootstrap_mean_interval(task_macro_f1),
        "localization_accuracy_ci95": bootstrap_mean_interval(task_localization),
    }


def _detection_metrics(items: list[AuditTrace]) -> dict:
    truth = {
        (trace.trace_id, segment_id, label)
        for trace in items
        for segment_id, labels in reference_labels(trace).items()
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
    detected_segments = {
        (trace_id, segment_id) for trace_id, segment_id, _ in detected
    }
    binary = classification_counts(truth_segments, detected_segments)
    localized_segments = truth_segments & detected_segments
    return {
        "reference_label_count": len(truth),
        "detected_label_count": len(detected),
        "precision": overall["precision"],
        "recall": overall["recall"],
        "f1": overall["f1"],
        "macro_f1": mean(macro_f1_values) if macro_f1_values else None,
        "binary": binary,
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
    reference_type = (
        "human_reference"
        if any(trace.reference_annotations for trace in final)
        else "injected_perturbation"
    )
    truth = [reference_bloat_ratio(trace) for trace in final]
    measured = [
        float(trace.metrics.get("detected_bloat_ratio", 0.0)) for trace in final
    ]
    by_task: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for trace, truth_value, measured_value in zip(final, truth, measured):
        by_task[trace.task_id].append((truth_value, measured_value))
    absolute_errors = [abs(a - b) for a, b in zip(truth, measured)]
    differences = [b - a for a, b in zip(truth, measured)]
    calibration = linear_calibration(measured, truth)
    rho_ci = cluster_bootstrap_interval(
        by_task,
        lambda pairs: spearman_correlation(
            [pair[0] for pair in pairs],
            [pair[1] for pair in pairs],
        ),
    )
    return {
        "sample_size": len(final),
        "task_sample_size": len(by_task),
        "reference_type": reference_type,
        "spearman_rho": spearman_correlation(truth, measured),
        "spearman_rho_ci95": rho_ci,
        "mean_absolute_error": mean(absolute_errors) if absolute_errors else None,
        "mean_reference_bloat_ratio": mean(truth) if truth else None,
        "mean_measured_bloat_ratio": mean(measured) if measured else None,
        "calibration": calibration,
        "bland_altman": bland_altman(differences),
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
    cluster_values: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"tokens": [], "ratios": [], "success": []}
    )
    for reduction, ratio, success, (before, _) in zip(
        token_reductions,
        token_reduction_ratios,
        success_differences,
        pairs,
    ):
        cluster = cluster_values[before.task_id]
        cluster["tokens"].append(reduction)
        cluster["ratios"].append(ratio)
        cluster["success"].append(success)
    cluster_token_reductions = [
        mean(values["tokens"]) for values in cluster_values.values()
    ]
    cluster_token_ratios = [
        mean(values["ratios"]) for values in cluster_values.values()
    ]
    cluster_success_differences = [
        mean(values["success"]) for values in cluster_values.values()
    ]
    improved = sum(
        1
        for before, after in pairs
        if not bool(before.task_success) and bool(after.task_success)
    )
    degraded = sum(
        1
        for before, after in pairs
        if bool(before.task_success) and not bool(after.task_success)
    )
    return {
        "pair_count": len(pairs),
        "cluster_count": len(cluster_values),
        "mean_token_reduction": mean(token_reductions) if token_reductions else None,
        "mean_token_reduction_ratio": (
            mean(token_reduction_ratios) if token_reduction_ratios else None
        ),
        "mean_task_success_difference": (
            mean(success_differences) if success_differences else None
        ),
        "task_success_difference_ci95": bootstrap_mean_interval(
            cluster_success_differences
        ),
        "token_reduction_ci95": bootstrap_mean_interval(
            cluster_token_reductions
        ),
        "token_reduction_ratio_ci95": bootstrap_mean_interval(
            cluster_token_ratios
        ),
        "mcnemar": {
            "improved": improved,
            "degraded": degraded,
            "exact_p_value": mcnemar_exact_p_value(improved, degraded),
            "interpretation": "exploratory_repetition_level_only",
        },
    }


def reference_labels(trace: AuditTrace) -> dict[str, tuple[str, ...]]:
    adjudicated = [
        annotation
        for annotation in trace.reference_annotations
        if annotation.adjudicated and annotation.decision == "remove"
    ]
    if adjudicated:
        return {
            annotation.segment_id: annotation.reasons or ("context_bloat",)
            for annotation in adjudicated
        }
    if trace.injected_labels:
        return {
            segment_id: tuple(labels)
            for segment_id, labels in trace.injected_labels.items()
        }
    return {
        segment_id: tuple(labels)
        for segment_id, labels in trace.ground_truth_labels.items()
    }


def reference_bloat_ratio(trace: AuditTrace) -> float:
    reference_ids = set(reference_labels(trace))
    total = sum(segment.token_count for segment in trace.segments)
    bloated = sum(
        segment.token_count
        for segment in trace.segments
        if segment.segment_id in reference_ids
    )
    return bloated / total if total else 0.0


def linear_calibration(
    predictor: list[float],
    outcome: list[float],
) -> dict[str, float | None]:
    if len(predictor) != len(outcome) or len(predictor) < 2:
        return {"intercept": None, "slope": None}
    predictor_mean = mean(predictor)
    denominator = sum((value - predictor_mean) ** 2 for value in predictor)
    if denominator == 0:
        return {"intercept": mean(outcome), "slope": None}
    slope = sum(
        (x - predictor_mean) * (y - mean(outcome))
        for x, y in zip(predictor, outcome)
    ) / denominator
    return {
        "intercept": mean(outcome) - slope * predictor_mean,
        "slope": slope,
    }


def bland_altman(differences: list[float]) -> dict[str, float | None]:
    if not differences:
        return {
            "mean_bias": None,
            "lower_limit_of_agreement": None,
            "upper_limit_of_agreement": None,
        }
    bias = mean(differences)
    if len(differences) == 1:
        standard_deviation = 0.0
    else:
        standard_deviation = math.sqrt(
            sum((value - bias) ** 2 for value in differences)
            / (len(differences) - 1)
        )
    return {
        "mean_bias": bias,
        "lower_limit_of_agreement": bias - 1.96 * standard_deviation,
        "upper_limit_of_agreement": bias + 1.96 * standard_deviation,
    }


def cluster_bootstrap_interval(
    values_by_task: dict[str, list[tuple[float, float]]],
    statistic: Callable[[list[tuple[float, float]]], float | None],
    *,
    samples: int = BOOTSTRAP_SAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> list[float] | None:
    task_ids = sorted(values_by_task)
    if not task_ids:
        return None
    generator = random.Random(seed)
    estimates: list[float] = []
    for _ in range(samples):
        sampled: list[tuple[float, float]] = []
        for _ in task_ids:
            sampled.extend(values_by_task[task_ids[generator.randrange(len(task_ids))]])
        value = statistic(sampled)
        if value is not None:
            estimates.append(float(value))
    if not estimates:
        return None
    estimates.sort()
    return [
        estimates[math.floor((len(estimates) - 1) * 0.025)],
        estimates[math.ceil((len(estimates) - 1) * 0.975)],
    ]


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


def bootstrap_mean_interval(
    values: list[float],
    *,
    samples: int = BOOTSTRAP_SAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> list[float] | None:
    if not values:
        return None
    if len(values) == 1 or len(set(values)) == 1:
        return [float(mean(values)), float(mean(values))]
    generator = random.Random(seed)
    count = len(values)
    estimates = sorted(
        mean(values[generator.randrange(count)] for _ in range(count))
        for _ in range(samples)
    )
    low = estimates[math.floor((len(estimates) - 1) * 0.025)]
    high = estimates[math.ceil((len(estimates) - 1) * 0.975)]
    return [low, high]


def percentile_interval(values: list[float]) -> list[float] | None:
    """Backward-compatible alias for the bootstrap interval of the mean."""
    return bootstrap_mean_interval(values)


def mcnemar_exact_p_value(improved: int, degraded: int) -> float | None:
    discordant = improved + degraded
    if discordant == 0:
        return None
    tail = min(improved, degraded)
    probability = sum(
        math.comb(discordant, index) for index in range(tail + 1)
    ) / (2**discordant)
    return min(1.0, 2.0 * probability)
