"""Context bloat detection and summary analysis."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import mean
from typing import Any

from .schema import AuditTrace, Segment
from .text_similarity import query_overlap_ratio


@dataclass(frozen=True)
class BloatThresholds:
    redundancy_ratio: float = 0.15
    source_dominance_ratio: float = 0.60
    growth_rate: float = 0.50
    min_growth_tokens: int = 50


def source_redundant_tokens(segments: list[Segment]) -> dict[str, int]:
    seen: set[str] = set()
    redundant_by_source: dict[str, int] = defaultdict(int)
    for segment in segments:
        if segment.normalized_hash in seen:
            redundant_by_source[segment.source_type] += segment.token_count
        else:
            seen.add(segment.normalized_hash)
    return dict(sorted(redundant_by_source.items()))


def classify_bloat(trace: AuditTrace, thresholds: BloatThresholds | None = None) -> list[str]:
    thresholds = thresholds or BloatThresholds()
    labels: list[str] = []
    metrics = trace.metrics

    if metrics.get("redundancy_ratio", 0.0) >= thresholds.redundancy_ratio:
        labels.append("high_redundancy")

    for source, ratio in metrics.get("source_ratios", {}).items():
        if ratio >= thresholds.source_dominance_ratio:
            labels.append(f"source_dominance:{source}")

    redundant_sources = source_redundant_tokens(trace.segments)
    for source, tokens in redundant_sources.items():
        if tokens > 0:
            labels.append(f"redundant_source:{source}")

    if trace.metrics.get("near_duplicate_segment_count", 0) > trace.metrics.get("duplicate_segment_count", 0):
        labels.append("near_duplicate_context")

    return sorted(set(labels))


def irrelevant_segments(trace: AuditTrace, query: str, threshold: float = 0.05) -> list[Segment]:
    return [
        segment
        for segment in trace.segments
        if segment.source_type in {"retrieval", "memory"} and query_overlap_ratio(segment.text, query) <= threshold
    ]


def summarize_traces(traces: list[AuditTrace]) -> dict[str, Any]:
    by_config: dict[str, list[AuditTrace]] = defaultdict(list)
    by_workflow: dict[str, list[AuditTrace]] = defaultdict(list)
    risk_flags = Counter()
    bloat_labels = Counter()

    previous_tokens_by_task: dict[str, int] = {}
    growth_rates: list[float] = []

    for trace in traces:
        by_config[trace.configuration].append(trace)
        by_workflow[trace.workflow_family].append(trace)
        risk_flags.update(trace.risk_flags)
        bloat_labels.update(classify_bloat(trace))

        previous = previous_tokens_by_task.get(trace.task_id)
        current = int(trace.metrics.get("total_tokens", 0))
        if previous and current >= previous:
            growth_rates.append((current - previous) / previous)
        previous_tokens_by_task[trace.task_id] = current

    def summarize_group(grouped: dict[str, list[AuditTrace]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, items in sorted(grouped.items()):
            scored = [trace for trace in items if trace.task_success is not None]
            result[name] = {
                "invocations": len(items),
                "mean_total_tokens": mean(trace.metrics.get("total_tokens", 0) for trace in items),
                "mean_total_chars": mean(trace.metrics.get("total_chars", 0) for trace in items),
                "mean_redundancy_ratio": mean(trace.metrics.get("redundancy_ratio", 0.0) for trace in items),
                "mean_near_redundancy_ratio": mean(trace.metrics.get("near_redundancy_ratio", 0.0) for trace in items),
                "mean_unique_information_ratio": mean(
                    trace.metrics.get("unique_information_ratio", 1.0) for trace in items
                ),
                "duplicate_segment_count": sum(trace.metrics.get("duplicate_segment_count", 0) for trace in items),
                "near_duplicate_segment_count": sum(
                    trace.metrics.get("near_duplicate_segment_count", 0) for trace in items
                ),
                "task_success_rate": (
                    sum(1 for trace in scored if trace.task_success) / len(scored) if scored else None
                ),
            }
        return result

    first_trace = traces[0] if traces else None
    return {
        "schema_version": first_trace.schema_version if first_trace else None,
        "experiment_id": first_trace.experiment_id if first_trace else None,
        "run_id": first_trace.run_id if first_trace else None,
        "dataset_name": first_trace.dataset_name if first_trace else None,
        "frameworks": sorted({trace.framework for trace in traces}),
        "providers": sorted({trace.provider for trace in traces}),
        "models": sorted({trace.model for trace in traces}),
        "trace_count": len(traces),
        "by_configuration": (by_configuration_summary := summarize_group(by_config)),
        "by_workflow_family": summarize_group(by_workflow),
        "mitigation_pairs": compare_mitigated_configurations(by_configuration_summary),
        "mean_context_growth_rate": mean(growth_rates) if growth_rates else 0.0,
        "risk_flags": dict(sorted(risk_flags.items())),
        "bloat_labels": dict(sorted(bloat_labels.items())),
    }


def compare_mitigated_configurations(by_configuration: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    pairs: dict[str, dict[str, Any]] = {}
    for config_name, mitigated in by_configuration.items():
        if not config_name.endswith("_mitigated"):
            continue
        original_name = config_name.removesuffix("_mitigated")
        original = by_configuration.get(original_name)
        if not original:
            continue
        pairs[f"{original_name} -> {config_name}"] = {
            "mean_total_tokens_before": original["mean_total_tokens"],
            "mean_total_tokens_after": mitigated["mean_total_tokens"],
            "mean_token_delta": mitigated["mean_total_tokens"] - original["mean_total_tokens"],
            "mean_redundancy_ratio_before": original["mean_redundancy_ratio"],
            "mean_redundancy_ratio_after": mitigated["mean_redundancy_ratio"],
            "redundancy_ratio_delta": mitigated["mean_redundancy_ratio"] - original["mean_redundancy_ratio"],
            "task_success_rate_before": original["task_success_rate"],
            "task_success_rate_after": mitigated["task_success_rate"],
        }
    return pairs
