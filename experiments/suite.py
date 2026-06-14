"""End-to-end experiment suite orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from context_auditor.bloat import summarize_traces
from context_auditor.framework_compare import compare_framework_summaries, write_framework_comparison_csv
from context_auditor.io import load_jsonl
from context_auditor.mitigation_eval import evaluate_mitigation_strategies, summarize_mitigation_rows
from context_auditor.reporting import write_mitigation_csv, write_summary_tables, write_svg_bar_charts

from .langchain_pilot import run_langchain_pilot
from .pilot import run_pilot


def run_experiment_suite(
    output_dir: str | Path = "artifacts",
    custom_config: str | Path = "configs/pilot.json",
    langchain_config: str | Path = "configs/langchain_pilot.json",
) -> dict[str, Path]:
    root = Path(output_dir)
    traces_dir = root / "traces"
    results_dir = root / "results"

    custom_trace_path = traces_dir / "pilot.jsonl"
    langchain_trace_path = traces_dir / "langchain_pilot.jsonl"
    custom_summary_path = results_dir / "pilot_summary.json"
    langchain_summary_path = results_dir / "langchain_pilot_summary.json"
    framework_comparison_json_path = results_dir / "framework_comparison.json"
    framework_comparison_csv_path = results_dir / "framework_comparison.csv"
    custom_mitigation_json_path = results_dir / "mitigation_report.json"
    custom_mitigation_csv_path = results_dir / "tables" / "mitigation_report.csv"
    langchain_mitigation_json_path = results_dir / "langchain_mitigation_report.json"
    langchain_mitigation_csv_path = results_dir / "langchain_tables" / "mitigation_report.csv"

    run_pilot(custom_trace_path, custom_config)
    run_langchain_pilot(langchain_trace_path, langchain_config)

    custom_summary = _write_summary_outputs(
        custom_trace_path,
        custom_summary_path,
        results_dir / "tables",
        results_dir / "charts",
    )
    langchain_summary = _write_summary_outputs(
        langchain_trace_path,
        langchain_summary_path,
        results_dir / "langchain_tables",
        results_dir / "langchain_charts",
    )

    comparison = compare_framework_summaries(
        {
            "custom-react": custom_summary,
            "langchain": langchain_summary,
        }
    )
    framework_comparison_json_path.parent.mkdir(parents=True, exist_ok=True)
    framework_comparison_json_path.write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")
    write_framework_comparison_csv(comparison, framework_comparison_csv_path)
    _write_mitigation_outputs(custom_trace_path, custom_mitigation_json_path, custom_mitigation_csv_path)
    _write_mitigation_outputs(langchain_trace_path, langchain_mitigation_json_path, langchain_mitigation_csv_path)

    return {
        "custom_trace_path": custom_trace_path,
        "langchain_trace_path": langchain_trace_path,
        "custom_summary_path": custom_summary_path,
        "langchain_summary_path": langchain_summary_path,
        "framework_comparison_json_path": framework_comparison_json_path,
        "framework_comparison_csv_path": framework_comparison_csv_path,
        "custom_mitigation_json_path": custom_mitigation_json_path,
        "custom_mitigation_csv_path": custom_mitigation_csv_path,
        "langchain_mitigation_json_path": langchain_mitigation_json_path,
        "langchain_mitigation_csv_path": langchain_mitigation_csv_path,
    }


def _write_summary_outputs(
    trace_path: Path,
    summary_path: Path,
    tables_dir: Path,
    charts_dir: Path,
) -> dict[str, Any]:
    traces = load_jsonl(trace_path)
    summary = summarize_traces(traces)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_summary_tables(summary, tables_dir)
    write_svg_bar_charts(summary, charts_dir)
    return summary


def _write_mitigation_outputs(trace_path: Path, json_path: Path, csv_path: Path) -> None:
    traces = load_jsonl(trace_path)
    rows = evaluate_mitigation_strategies(traces)
    summary = summarize_mitigation_rows(rows)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    write_mitigation_csv(rows, csv_path)
