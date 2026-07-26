"""Cross-framework comparison over aligned experiment summaries."""

from __future__ import annotations

from typing import Any


class CompareFrameworks:
    def execute(
        self,
        baseline: dict[str, Any],
        comparison: dict[str, Any],
    ) -> dict[str, Any]:
        baseline_groups = baseline.get("by_configuration", {})
        comparison_groups = comparison.get("by_configuration", {})
        common = sorted(set(baseline_groups) & set(comparison_groups))
        rows = []
        for name in common:
            left = baseline_groups[name]
            right = comparison_groups[name]
            rows.append(
                {
                    "configuration": name,
                    "baseline_framework": first(baseline.get("frameworks")),
                    "comparison_framework": first(comparison.get("frameworks")),
                    "baseline_mean_total_tokens": left["mean_total_tokens"],
                    "comparison_mean_total_tokens": right["mean_total_tokens"],
                    "mean_total_tokens_delta": (
                        right["mean_total_tokens"] - left["mean_total_tokens"]
                    ),
                    "baseline_mean_redundancy_ratio": left["mean_redundancy_ratio"],
                    "comparison_mean_redundancy_ratio": right["mean_redundancy_ratio"],
                    "mean_redundancy_ratio_delta": (
                        right["mean_redundancy_ratio"] - left["mean_redundancy_ratio"]
                    ),
                    "baseline_task_success_rate": left["task_success_rate"],
                    "comparison_task_success_rate": right["task_success_rate"],
                    "task_success_rate_delta": nullable_delta(
                        left["task_success_rate"], right["task_success_rate"]
                    ),
                }
            )
        return {
            "schema_version": "1.0.0",
            "baseline_framework": first(baseline.get("frameworks")),
            "comparison_framework": first(comparison.get("frameworks")),
            "row_count": len(rows),
            "rows": rows,
        }


def first(values: list[str] | None) -> str:
    return values[0] if values else "unknown"


def nullable_delta(left: float | None, right: float | None) -> float | None:
    return right - left if left is not None and right is not None else None
