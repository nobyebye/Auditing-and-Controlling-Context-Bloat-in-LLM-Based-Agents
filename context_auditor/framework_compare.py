"""Cross-framework comparison helpers for thesis experiment summaries."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


COMPARISON_FIELDNAMES = [
    "configuration",
    "baseline_framework",
    "comparison_framework",
    "baseline_mean_total_tokens",
    "comparison_mean_total_tokens",
    "mean_total_tokens_delta",
    "baseline_mean_redundancy_ratio",
    "comparison_mean_redundancy_ratio",
    "mean_redundancy_ratio_delta",
    "baseline_task_success_rate",
    "comparison_task_success_rate",
    "task_success_rate_delta",
]


def compare_framework_summaries(summaries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    frameworks = sorted(summaries)
    if len(frameworks) < 2:
        return {"frameworks": frameworks, "configuration_count": 0, "rows": []}

    baseline_framework = frameworks[0]
    rows: list[dict[str, Any]] = []
    baseline_configs = summaries[baseline_framework].get("by_configuration", {})
    for comparison_framework in frameworks[1:]:
        comparison_configs = summaries[comparison_framework].get("by_configuration", {})
        for configuration in sorted(set(baseline_configs) & set(comparison_configs)):
            baseline = baseline_configs[configuration]
            comparison = comparison_configs[configuration]
            rows.append(
                {
                    "configuration": configuration,
                    "baseline_framework": baseline_framework,
                    "comparison_framework": comparison_framework,
                    "baseline_mean_total_tokens": baseline.get("mean_total_tokens"),
                    "comparison_mean_total_tokens": comparison.get("mean_total_tokens"),
                    "mean_total_tokens_delta": _delta(
                        comparison.get("mean_total_tokens"),
                        baseline.get("mean_total_tokens"),
                    ),
                    "baseline_mean_redundancy_ratio": baseline.get("mean_redundancy_ratio"),
                    "comparison_mean_redundancy_ratio": comparison.get("mean_redundancy_ratio"),
                    "mean_redundancy_ratio_delta": _delta(
                        comparison.get("mean_redundancy_ratio"),
                        baseline.get("mean_redundancy_ratio"),
                    ),
                    "baseline_task_success_rate": baseline.get("task_success_rate"),
                    "comparison_task_success_rate": comparison.get("task_success_rate"),
                    "task_success_rate_delta": _delta(
                        comparison.get("task_success_rate"),
                        baseline.get("task_success_rate"),
                    ),
                }
            )

    return {
        "frameworks": frameworks,
        "configuration_count": len({row["configuration"] for row in rows}),
        "rows": rows,
    }


def write_framework_comparison_csv(comparison: dict[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMPARISON_FIELDNAMES)
        writer.writeheader()
        for row in comparison.get("rows", []):
            writer.writerow(row)


def _delta(current: float | int | None, baseline: float | int | None) -> float | None:
    if current is None or baseline is None:
        return None
    return current - baseline
