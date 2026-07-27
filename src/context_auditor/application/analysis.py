"""Trace aggregation for experiment reports."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from statistics import mean
from typing import Any, Iterable

from context_auditor.application.evaluation import (
    evaluate_detection,
    evaluate_measurement,
    evaluate_mitigation,
    bootstrap_mean_interval,
    reference_labels,
    reference_bloat_ratio,
)
from context_auditor.domain.models import AuditTrace, SCHEMA_VERSION


class AnalyzeBloat:
    def execute(self, traces: Iterable[AuditTrace]) -> dict[str, Any]:
        items = list(traces)
        primary = [trace for trace in items if trace.analysis_cohort == "primary"]
        inferential_items = primary or items
        inferential_cohort = "primary" if primary else (
            inferential_items[0].analysis_cohort if inferential_items else "none"
        )
        groups: dict[str, list[AuditTrace]] = defaultdict(list)
        workflows: dict[str, list[AuditTrace]] = defaultdict(list)
        frameworks: dict[str, list[AuditTrace]] = defaultdict(list)
        cohorts: dict[str, list[AuditTrace]] = defaultdict(list)
        for trace in items:
            groups[trace.configuration].append(trace)
            workflows[trace.workflow_family].append(trace)
            frameworks[trace.framework].append(trace)
            cohorts[trace.analysis_cohort].append(trace)
        source_bloat = self._source_bloat(inferential_items)
        return {
            "schema_version": SCHEMA_VERSION,
            "trace_count": len(items),
            "task_count": len({trace.task_id for trace in items}),
            "inferential_trace_count": len(inferential_items),
            "inferential_task_count": len(
                {trace.task_id for trace in inferential_items}
            ),
            "inferential_cohort": inferential_cohort,
            "frameworks": sorted({trace.framework for trace in items}),
            "providers": sorted({trace.provider for trace in items}),
            "models": sorted({trace.model for trace in items}),
            "dataset_splits": sorted({trace.dataset_split for trace in items}),
            "provider_usage": self._provider_usage(items),
            "by_configuration": {
                name: self._summarize(group) for name, group in sorted(groups.items())
            },
            "by_workflow_family": {
                name: self._summarize(group) for name, group in sorted(workflows.items())
            },
            "by_framework": {
                name: self._summarize(group) for name, group in sorted(frameworks.items())
            },
            "by_analysis_cohort": {
                name: self._summarize(group) for name, group in sorted(cohorts.items())
            },
            "cohort_evidence": {
                name: self._cohort_evidence(group)
                for name, group in sorted(cohorts.items())
            },
            "risk_flags": dict(
                sorted(Counter(flag for trace in items for flag in trace.risk_flags).items())
            ),
            "detection": evaluate_detection(inferential_items),
            "measurement": evaluate_measurement(inferential_items),
            "mitigation_effect": evaluate_mitigation(inferential_items),
            "source_bloat": source_bloat,
            "workflow_bloat": self._workflow_bloat(inferential_items),
            "mitigation": self._mitigation_summary(inferential_items),
        }

    def _cohort_evidence(self, traces: list[AuditTrace]) -> dict[str, Any]:
        return {
            "trace_count": len(traces),
            "task_count": len({trace.task_id for trace in traces}),
            "detection": evaluate_detection(traces),
            "measurement": evaluate_measurement(traces),
            "mitigation_effect": evaluate_mitigation(traces),
            "source_bloat": self._source_bloat(traces),
        }

    @staticmethod
    def _summarize(traces: list[AuditTrace]) -> dict[str, Any]:
        final = [trace for trace in traces if trace.task_success is not None]
        growth_rates: list[float] = []
        sequences: dict[tuple[str, int], list[AuditTrace]] = defaultdict(list)
        for trace in traces:
            sequences[(trace.task_id, trace.repetition_id)].append(trace)
        for sequence in sequences.values():
            ordered = sorted(sequence, key=lambda trace: trace.invocation_index)
            for previous, current in zip(ordered, ordered[1:]):
                before = float(previous.metrics.get("total_tokens", 0))
                after = float(current.metrics.get("total_tokens", 0))
                if before:
                    growth_rates.append((after - before) / before)
        return {
            "trace_count": len(traces),
            "task_count": len({trace.task_id for trace in traces}),
            "mean_total_tokens": mean(
                float(trace.metrics.get("total_tokens", 0)) for trace in traces
            )
            if traces
            else 0.0,
            "mean_redundancy_ratio": mean(
                float(trace.metrics.get("redundancy_ratio", 0.0)) for trace in traces
            )
            if traces
            else 0.0,
            "mean_near_redundancy_ratio": mean(
                float(trace.metrics.get("near_redundancy_ratio", 0.0)) for trace in traces
            )
            if traces
            else 0.0,
            "task_success_rate": (
                sum(1 for trace in final if trace.task_success) / len(final) if final else None
            ),
            "mean_context_growth_rate": mean(growth_rates) if growth_rates else 0.0,
        }

    @staticmethod
    def _mitigation_summary(traces: list[AuditTrace]) -> dict[str, Any]:
        by_configuration: dict[str, dict[str, int]] = defaultdict(
            lambda: {"decisions": 0, "removed_tokens": 0, "affected_traces": 0}
        )
        for trace in traces:
            if not trace.mitigation_decisions:
                continue
            row = by_configuration[trace.configuration]
            row["decisions"] += len(trace.mitigation_decisions)
            row["removed_tokens"] += sum(
                decision.removed_tokens for decision in trace.mitigation_decisions
            )
            row["affected_traces"] += 1
        return dict(sorted(by_configuration.items()))

    @staticmethod
    def _provider_usage(traces: list[AuditTrace]) -> dict[str, Any]:
        usages = [trace.provider_usage for trace in traces if trace.provider_usage]
        latencies = [
            float(trace.latency_ms)
            for trace in traces
            if trace.latency_ms is not None
        ]
        return {
            "input_tokens": sum(item.input_tokens or 0 for item in usages),
            "output_tokens": sum(item.output_tokens or 0 for item in usages),
            "total_tokens": sum(item.total_tokens or 0 for item in usages),
            "cost_usd": sum(item.cost_usd or 0.0 for item in usages),
            "mean_latency_ms": mean(latencies) if latencies else None,
        }

    @staticmethod
    def _source_bloat(traces: list[AuditTrace]) -> dict[str, dict[str, Any]]:
        totals: dict[str, int] = defaultdict(int)
        bloated: dict[str, int] = defaultdict(int)
        trace_ratios: dict[str, list[float]] = defaultdict(list)
        task_ratios: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for trace in traces:
            truth_ids = set(reference_labels(trace))
            trace_total: dict[str, int] = defaultdict(int)
            trace_bloat: dict[str, int] = defaultdict(int)
            for segment in trace.segments:
                trace_total[segment.source_type] += segment.token_count
                if segment.segment_id in truth_ids:
                    trace_bloat[segment.source_type] += segment.token_count
            for source, tokens in trace_total.items():
                totals[source] += tokens
                bloated[source] += trace_bloat[source]
                trace_ratios[source].append(
                    trace_bloat[source] / tokens if tokens else 0.0
                )
                task_ratios[source][trace.task_id].append(
                    trace_bloat[source] / tokens if tokens else 0.0
                )
        return {
            source: {
                "total_tokens": float(totals[source]),
                "bloat_tokens": float(bloated[source]),
                "bloat_ratio": (
                    bloated[source] / totals[source] if totals[source] else 0.0
                ),
                "mean_bloat_ratio": mean(trace_ratios[source]),
                "mean_bloat_ratio_ci95": bootstrap_mean_interval(
                    [
                        mean(values)
                        for values in task_ratios[source].values()
                    ]
                ),
                "task_count": len(task_ratios[source]),
            }
            for source in sorted(totals)
        }

    @staticmethod
    def _workflow_bloat(traces: list[AuditTrace]) -> dict[str, Any]:
        task_values: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for trace in traces:
            if trace.task_success is None:
                continue
            task_values[trace.workflow_family][trace.task_id].append(
                reference_bloat_ratio(trace)
            )
        summaries = {}
        flattened = {}
        for workflow, tasks in sorted(task_values.items()):
            values = [mean(items) for items in tasks.values()]
            flattened[workflow] = values
            summaries[workflow] = {
                "task_count": len(values),
                "mean_human_reference_bloat_ratio": (
                    mean(values) if values else None
                ),
                "ci95": bootstrap_mean_interval(values),
            }
        effects = []
        names = sorted(flattened)
        for index, left in enumerate(names):
            for right in names[index + 1 :]:
                effects.append(
                    {
                        "left": left,
                        "right": right,
                        "mean_difference": (
                            mean(flattened[left]) - mean(flattened[right])
                        ),
                        "hedges_g": hedges_g(
                            flattened[left],
                            flattened[right],
                        ),
                    }
                )
        return {"by_workflow": summaries, "pairwise_effects": effects}


def hedges_g(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(right) < 2:
        return None
    left_mean = mean(left)
    right_mean = mean(right)
    pooled_denominator = len(left) + len(right) - 2
    pooled_variance = (
        sum((value - left_mean) ** 2 for value in left)
        + sum((value - right_mean) ** 2 for value in right)
    ) / pooled_denominator
    if pooled_variance <= 0:
        return 0.0
    correction = 1 - 3 / (4 * (len(left) + len(right)) - 9)
    return correction * (left_mean - right_mean) / math.sqrt(pooled_variance)
