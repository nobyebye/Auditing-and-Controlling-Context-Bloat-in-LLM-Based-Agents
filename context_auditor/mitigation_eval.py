"""Before/after mitigation evaluation over final task invocations."""

from __future__ import annotations

from collections import defaultdict
from typing import Callable

from .mitigation import (
    MitigationReport,
    filter_irrelevant_segments,
    remove_exact_duplicate_segments,
    remove_near_duplicate_segments,
)
from .schema import AuditTrace, Segment

MitigationFn = Callable[[AuditTrace], tuple[list[Segment], MitigationReport]]


def final_invocations(traces: list[AuditTrace]) -> list[AuditTrace]:
    by_task: dict[str, AuditTrace] = {}
    for trace in traces:
        current = by_task.get(trace.task_id)
        if current is None or trace.invocation_index > current.invocation_index:
            by_task[trace.task_id] = trace
    return list(by_task.values())


def evaluate_mitigation_strategies(traces: list[AuditTrace]) -> list[dict]:
    strategies: dict[str, MitigationFn] = {
        "exact_duplicate_removal": lambda trace: remove_exact_duplicate_segments(trace),
        "near_duplicate_removal": lambda trace: remove_near_duplicate_segments(trace),
        "irrelevant_context_filter": lambda trace: filter_irrelevant_segments(trace, _query_from_trace(trace)),
    }

    rows: list[dict] = []
    for trace in final_invocations(traces):
        for strategy_name, strategy in strategies.items():
            kept_segments, report = strategy(trace)
            rows.append(
                {
                    "strategy": strategy_name,
                    "trace_id": trace.trace_id,
                    "task_id": trace.task_id,
                    "configuration": trace.configuration,
                    "workflow_family": trace.workflow_family,
                    "task_success": trace.task_success,
                    "post_mitigation_success_proxy": _post_mitigation_success_proxy(trace, kept_segments, report),
                    "original_tokens": report.original_tokens,
                    "mitigated_tokens": report.mitigated_tokens,
                    "removed_segments": report.removed_segments,
                    "removed_tokens": report.removed_tokens,
                    "removed_by_source": report.removed_by_source,
                    "token_reduction_ratio": report.token_reduction_ratio,
                }
            )
    return rows


def summarize_mitigation_rows(rows: list[dict]) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["strategy"]].append(row)

    summary: dict[str, dict] = {}
    for strategy, items in sorted(grouped.items()):
        scored = [item for item in items if item["task_success"] is not None]
        post_scored = [item for item in items if item["post_mitigation_success_proxy"] is not None]
        originally_successful = [item for item in items if item["task_success"] is True]
        summary[strategy] = {
            "evaluated_tasks": len(items),
            "affected_tasks": sum(1 for item in items if item["removed_segments"]),
            "total_removed_tokens": sum(item["removed_tokens"] for item in items),
            "mean_token_reduction_ratio": (
                sum(item["token_reduction_ratio"] for item in items) / len(items) if items else 0.0
            ),
            "task_success_rate": (
                sum(1 for item in scored if item["task_success"]) / len(scored) if scored else None
            ),
            "post_mitigation_success_proxy_rate": (
                sum(1 for item in post_scored if item["post_mitigation_success_proxy"]) / len(post_scored)
                if post_scored
                else None
            ),
            "success_preservation_proxy_rate": (
                sum(1 for item in originally_successful if item["post_mitigation_success_proxy"])
                / len(originally_successful)
                if originally_successful
                else None
            ),
        }
    return summary


def _query_from_trace(trace: AuditTrace) -> str:
    user_segments = [segment.text for segment in trace.segments if segment.source_type == "user"]
    return user_segments[-1] if user_segments else ""


def _post_mitigation_success_proxy(
    trace: AuditTrace,
    kept_segments: list[Segment],
    report: MitigationReport,
) -> bool | None:
    if trace.task_success is None:
        return None
    if not trace.task_success:
        return False
    if report.removed_segments == 0:
        return True
    expected = trace.task_expected_keyword
    if not expected:
        return trace.task_success
    expected_lower = expected.lower()
    non_generated_support = [
        segment
        for segment in kept_segments
        if segment.source_type != "generated_trace" and expected_lower in segment.text.lower()
    ]
    return bool(non_generated_support)
