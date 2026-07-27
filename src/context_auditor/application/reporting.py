"""Build named CSV, JSON, and SVG run artifacts."""

from __future__ import annotations

import csv
import html
from pathlib import Path
from typing import Any, Iterable

from context_auditor.adapters.storage.serialization import write_json_atomic
from context_auditor.application.conclusions import BuildRQEvidence
from context_auditor.domain.models import AuditTrace


class BuildReport:
    def execute(
        self,
        traces: Iterable[AuditTrace],
        summary: dict[str, Any],
        *,
        invocation_csv: Path,
        task_csv: Path,
        summary_json: Path,
        rq_evidence_json: Path | None = None,
        rq_rules: dict[str, Any] | None = None,
        tables_dir: Path,
        figures_dir: Path,
    ) -> None:
        items = list(traces)
        self._write_invocations(items, invocation_csv)
        self._write_tasks(items, task_csv)
        write_json_atomic(summary_json, summary)
        if rq_evidence_json is not None and rq_rules is not None:
            write_json_atomic(
                rq_evidence_json,
                BuildRQEvidence().execute(summary, rq_rules),
            )
        self._write_group_table(summary["by_configuration"], tables_dir / "by_configuration.csv")
        self._write_group_table(summary["by_workflow_family"], tables_dir / "by_workflow_family.csv")
        self._write_group_table(
            summary.get("by_analysis_cohort", {}),
            tables_dir / "by_analysis_cohort.csv",
        )
        self._write_mitigation_table(
            summary.get("mitigation", {}),
            tables_dir / "mitigation_by_configuration.csv",
        )
        self._write_detection_table(
            summary.get("detection", {}).get("by_label", {}),
            tables_dir / "detection_by_label.csv",
        )
        self._write_source_bloat_table(
            summary.get("source_bloat", {}),
            tables_dir / "source_bloat.csv",
        )
        self._write_bar_chart(
            {
                name: values["mean_total_tokens"]
                for name, values in summary["by_configuration"].items()
            },
            figures_dir / "tokens_by_configuration.svg",
            "Mean tokens by configuration",
        )
        self._write_bar_chart(
            {
                name: values["mean_redundancy_ratio"]
                for name, values in summary["by_configuration"].items()
            },
            figures_dir / "redundancy_by_configuration.svg",
            "Mean redundancy ratio by configuration",
        )

    @staticmethod
    def _write_invocations(traces: list[AuditTrace], path: Path) -> None:
        fields = (
            "trace_id",
            "task_id",
            "workflow_family",
            "analysis_cohort",
            "configuration",
            "repetition_id",
            "invocation_index",
            "total_tokens",
            "redundancy_ratio",
            "duplicate_segment_count",
            "task_success",
            "latency_ms",
            "evidence_tier",
            "injected_bloat_ratio",
            "human_reference_bloat_ratio",
            "detected_bloat_ratio",
            "nonredundant_token_ratio",
            "input_tokens",
            "output_tokens",
            "cost_usd",
            "system_tokens",
            "user_tokens",
            "framework_tokens",
            "retrieval_tokens",
            "memory_tokens",
            "tool_tokens",
            "generated_trace_tokens",
        )
        rows = [
            {
                "trace_id": trace.trace_id,
                "task_id": trace.task_id,
                "workflow_family": trace.workflow_family,
                "analysis_cohort": trace.analysis_cohort,
                "configuration": trace.configuration,
                "repetition_id": trace.repetition_id,
                "invocation_index": trace.invocation_index,
                "total_tokens": trace.metrics.get("total_tokens", 0),
                "redundancy_ratio": trace.metrics.get("redundancy_ratio", 0.0),
                "duplicate_segment_count": trace.metrics.get("duplicate_segment_count", 0),
                "task_success": trace.task_success,
                "latency_ms": trace.latency_ms,
                "evidence_tier": trace.evidence_tier,
                "injected_bloat_ratio": trace.metrics.get(
                    "injected_bloat_ratio",
                    trace.metrics.get("ground_truth_bloat_ratio", 0.0),
                ),
                "human_reference_bloat_ratio": trace.metrics.get(
                    "human_reference_bloat_ratio", 0.0
                ),
                "detected_bloat_ratio": trace.metrics.get(
                    "detected_bloat_ratio", 0.0
                ),
                "nonredundant_token_ratio": trace.metrics.get(
                    "nonredundant_token_ratio", 0.0
                ),
                "input_tokens": (
                    trace.provider_usage.input_tokens if trace.provider_usage else None
                ),
                "output_tokens": (
                    trace.provider_usage.output_tokens if trace.provider_usage else None
                ),
                "cost_usd": trace.provider_usage.cost_usd if trace.provider_usage else None,
                **{
                    f"{source}_tokens": trace.metrics.get("tokens_by_source", {}).get(
                        source, 0
                    )
                    for source in (
                        "system",
                        "user",
                        "framework",
                        "retrieval",
                        "memory",
                        "tool",
                        "generated_trace",
                    )
                },
            }
            for trace in traces
        ]
        write_csv(path, fields, rows)

    @staticmethod
    def _write_tasks(traces: list[AuditTrace], path: Path) -> None:
        final = [trace for trace in traces if trace.task_success is not None]
        fields = (
            "task_id",
            "workflow_family",
            "analysis_cohort",
            "configuration",
            "repetition_id",
            "task_success",
            "task_output",
            "expected_answer",
            "score",
            "scoring_method",
            "framework",
        )
        write_csv(
            path,
            fields,
            [
                {
                    "task_id": trace.task_id,
                    "workflow_family": trace.workflow_family,
                    "analysis_cohort": trace.analysis_cohort,
                    "configuration": trace.configuration,
                    "repetition_id": trace.repetition_id,
                    "task_success": trace.task_success,
                    "task_output": trace.task_output,
                    "expected_answer": trace.expected_answer,
                    "score": trace.scoring.score if trace.scoring else None,
                    "scoring_method": trace.scoring.method if trace.scoring else None,
                    "framework": trace.framework,
                }
                for trace in final
            ],
        )

    @staticmethod
    def _write_group_table(groups: dict[str, dict[str, Any]], path: Path) -> None:
        fields = (
            "name",
            "trace_count",
            "task_count",
            "mean_total_tokens",
            "mean_redundancy_ratio",
            "mean_near_redundancy_ratio",
            "task_success_rate",
            "mean_context_growth_rate",
        )
        write_csv(
            path,
            fields,
            [{"name": name, **values} for name, values in groups.items()],
        )

    @staticmethod
    def _write_mitigation_table(groups: dict[str, dict[str, Any]], path: Path) -> None:
        write_csv(
            path,
            ("configuration", "decisions", "removed_tokens", "affected_traces"),
            [{"configuration": name, **values} for name, values in groups.items()],
        )

    @staticmethod
    def _write_detection_table(groups: dict[str, dict[str, Any]], path: Path) -> None:
        write_csv(
            path,
            (
                "label",
                "true_positive",
                "false_positive",
                "false_negative",
                "precision",
                "recall",
                "f1",
            ),
            [{"label": label, **values} for label, values in groups.items()],
        )

    @staticmethod
    def _write_source_bloat_table(groups: dict[str, dict[str, Any]], path: Path) -> None:
        write_csv(
            path,
            (
                "source",
                "total_tokens",
                "bloat_tokens",
                "bloat_ratio",
                "mean_bloat_ratio",
            ),
            [{"source": source, **values} for source, values in groups.items()],
        )

    @staticmethod
    def _write_bar_chart(values: dict[str, float], path: Path, title: str) -> None:
        width = 1000
        row_height = 34
        height = max(120, 70 + len(values) * row_height)
        maximum = max(values.values(), default=1.0) or 1.0
        bars: list[str] = []
        for index, (name, value) in enumerate(values.items()):
            y = 55 + index * row_height
            length = int((value / maximum) * 560)
            bars.append(
                f'<text x="15" y="{y + 16}" font-size="12">{html.escape(name)}</text>'
                f'<rect x="320" y="{y}" width="{length}" height="20" fill="#287271"/>'
                f'<text x="{328 + length}" y="{y + 15}" font-size="11">{value:.3f}</text>'
            )
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
            '<rect width="100%" height="100%" fill="white"/>'
            f'<text x="15" y="28" font-size="18" font-weight="bold">{html.escape(title)}</text>'
            + "".join(bars)
            + "</svg>"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(svg, encoding="utf-8")


def write_csv(
    path: Path,
    fields: tuple[str, ...],
    rows: Iterable[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)
