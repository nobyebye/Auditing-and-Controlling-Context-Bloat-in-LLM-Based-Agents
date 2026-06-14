"""Command-line interface for the context bloat auditor."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from ._version import __version__
from .bloat import summarize_traces
from .io import load_jsonl
from .mitigation import remove_exact_duplicate_segments
from .mitigation_eval import evaluate_mitigation_strategies, summarize_mitigation_rows
from .reporting import write_summary_tables, write_svg_bar_charts


def run_pilot_command(args: argparse.Namespace) -> None:
    from experiments.pilot import run_pilot

    run_pilot(args.out, args.config)
    print(f"Wrote traces to {args.out}")


def run_langchain_pilot_command(args: argparse.Namespace) -> None:
    from experiments.langchain_pilot import run_langchain_pilot

    run_langchain_pilot(args.out, args.config)
    print(f"Wrote LangChain-compatible traces to {args.out}")


def analyze_command(args: argparse.Namespace) -> None:
    traces = load_jsonl(args.trace_path)
    summary = summarize_traces(traces)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.tables_dir:
        write_summary_tables(summary, args.tables_dir)
    if args.charts_dir:
        write_svg_bar_charts(summary, args.charts_dir)
    print(f"Wrote summary to {output}")


def mitigate_command(args: argparse.Namespace) -> None:
    traces = load_jsonl(args.trace_path)
    reports = evaluate_mitigation_strategies(traces)
    summary = summarize_mitigation_rows(reports)

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"summary": summary, "rows": reports}, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.csv_out:
        _write_mitigation_csv(reports, Path(args.csv_out))
    print(f"Wrote mitigation report to {output}")


def _write_mitigation_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "strategy",
        "trace_id",
        "task_id",
        "configuration",
        "workflow_family",
        "task_success",
        "post_mitigation_success_proxy",
        "original_tokens",
        "mitigated_tokens",
        "removed_segments",
        "removed_tokens",
        "removed_by_source",
        "token_reduction_ratio",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="context-auditor")
    parser.add_argument("--version", action="version", version=f"context-auditor {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    pilot = subparsers.add_parser("run-pilot", help="Run controlled pilot experiments.")
    pilot.add_argument("--out", default="traces/pilot.jsonl", help="Output JSONL trace path.")
    pilot.add_argument("--config", default="configs/pilot.json", help="Experiment configuration JSON path.")
    pilot.set_defaults(func=run_pilot_command)

    langchain_pilot = subparsers.add_parser(
        "run-langchain-pilot",
        help="Run controlled LangChain-compatible pilot experiments.",
    )
    langchain_pilot.add_argument("--out", default="traces/langchain_pilot.jsonl", help="Output JSONL trace path.")
    langchain_pilot.add_argument(
        "--config",
        default="configs/langchain_pilot.json",
        help="Experiment configuration JSON path.",
    )
    langchain_pilot.set_defaults(func=run_langchain_pilot_command)

    analyze = subparsers.add_parser("analyze", help="Summarize a JSONL trace file.")
    analyze.add_argument("trace_path")
    analyze.add_argument("--out", default="results/summary.json")
    analyze.add_argument("--tables-dir", default="results/tables")
    analyze.add_argument("--charts-dir", default="results/charts")
    analyze.set_defaults(func=analyze_command)

    mitigate = subparsers.add_parser("mitigate", help="Evaluate mitigation strategies on final task invocations.")
    mitigate.add_argument("trace_path")
    mitigate.add_argument("--out", default="results/mitigation_report.json")
    mitigate.add_argument("--csv-out", default="results/tables/mitigation_report.csv")
    mitigate.set_defaults(func=mitigate_command)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
