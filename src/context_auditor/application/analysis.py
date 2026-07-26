"""Trace aggregation for experiment reports."""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Any, Iterable

from context_auditor.domain.models import AuditTrace


class AnalyzeBloat:
    def execute(self, traces: Iterable[AuditTrace]) -> dict[str, Any]:
        items = list(traces)
        groups: dict[str, list[AuditTrace]] = defaultdict(list)
        workflows: dict[str, list[AuditTrace]] = defaultdict(list)
        for trace in items:
            groups[trace.configuration].append(trace)
            workflows[trace.workflow_family].append(trace)
        return {
            "schema_version": "1.0.0",
            "trace_count": len(items),
            "task_count": len({trace.task_id for trace in items}),
            "frameworks": sorted({trace.framework for trace in items}),
            "providers": sorted({trace.provider for trace in items}),
            "models": sorted({trace.model for trace in items}),
            "by_configuration": {
                name: self._summarize(group) for name, group in sorted(groups.items())
            },
            "by_workflow_family": {
                name: self._summarize(group) for name, group in sorted(workflows.items())
            },
            "risk_flags": dict(
                sorted(Counter(flag for trace in items for flag in trace.risk_flags).items())
            ),
            "mitigation": self._mitigation_summary(items),
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
