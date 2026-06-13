"""Context bloat detection and summary analysis."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import mean
from typing import Any

from .schema import AuditTrace, Segment


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

    return sorted(set(labels))


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
            result[name] = {
                "invocations": len(items),
                "mean_total_tokens": mean(trace.metrics.get("total_tokens", 0) for trace in items),
                "mean_total_chars": mean(trace.metrics.get("total_chars", 0) for trace in items),
                "mean_redundancy_ratio": mean(trace.metrics.get("redundancy_ratio", 0.0) for trace in items),
                "mean_unique_information_ratio": mean(
                    trace.metrics.get("unique_information_ratio", 1.0) for trace in items
                ),
                "duplicate_segment_count": sum(trace.metrics.get("duplicate_segment_count", 0) for trace in items),
            }
        return result

    return {
        "trace_count": len(traces),
        "by_configuration": summarize_group(by_config),
        "by_workflow_family": summarize_group(by_workflow),
        "mean_context_growth_rate": mean(growth_rates) if growth_rates else 0.0,
        "risk_flags": dict(sorted(risk_flags.items())),
        "bloat_labels": dict(sorted(bloat_labels.items())),
    }

