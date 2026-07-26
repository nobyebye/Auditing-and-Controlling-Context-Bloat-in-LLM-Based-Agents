"""Trace aggregation for experiment reports."""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Any, Iterable

from context_auditor.application.evaluation import (
    evaluate_detection,
    evaluate_measurement,
    evaluate_mitigation,
)
from context_auditor.domain.models import AuditTrace


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
            "schema_version": "1.1.0",
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
    def _source_bloat(traces: list[AuditTrace]) -> dict[str, dict[str, float]]:
        totals: dict[str, int] = defaultdict(int)
        bloated: dict[str, int] = defaultdict(int)
        trace_ratios: dict[str, list[float]] = defaultdict(list)
        for trace in traces:
            truth_ids = set(trace.ground_truth_labels)
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
        return {
            source: {
                "total_tokens": float(totals[source]),
                "bloat_tokens": float(bloated[source]),
                "bloat_ratio": (
                    bloated[source] / totals[source] if totals[source] else 0.0
                ),
                "mean_bloat_ratio": mean(trace_ratios[source]),
            }
            for source in sorted(totals)
        }
