"""Command-line interface for the context bloat auditor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ._version import __version__
from .bloat import summarize_traces
from .io import load_jsonl
from .mitigation import remove_exact_duplicate_segments
from .mitigation_eval import evaluate_mitigation_strategies, summarize_mitigation_rows
from .reporting import write_mitigation_csv, write_summary_tables, write_svg_bar_charts


def run_pilot_command(args: argparse.Namespace) -> None:
    from experiments.pilot import run_pilot

    run_pilot(args.out, args.config)
    print(f"Wrote traces to {args.out}")


def run_langchain_pilot_command(args: argparse.Namespace) -> None:
    from experiments.langchain_pilot import run_langchain_pilot

    run_langchain_pilot(args.out, args.config)
    print(f"Wrote LangChain-compatible traces to {args.out}")


def run_suite_command(args: argparse.Namespace) -> None:
    from experiments.suite import run_experiment_suite

    outputs = run_experiment_suite(args.out_dir, args.custom_config, args.langchain_config)
    print(f"Wrote experiment suite outputs to {args.out_dir}")
    print(f"Wrote run manifest to {outputs['manifest_path']}")
    print(f"Wrote framework comparison to {outputs['framework_comparison_csv_path']}")


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
        write_mitigation_csv(reports, Path(args.csv_out))
    print(f"Wrote mitigation report to {output}")


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

    suite = subparsers.add_parser(
        "run-suite",
        help="Run custom and LangChain-compatible pilots and write cross-framework comparison outputs.",
    )
    suite.add_argument("--out-dir", default="artifacts", help="Output directory for traces, summaries, tables, and comparison files.")
    suite.add_argument("--custom-config", default="configs/pilot.json", help="Custom ReAct experiment configuration JSON path.")
    suite.add_argument(
        "--langchain-config",
        default="configs/langchain_pilot.json",
        help="LangChain-compatible experiment configuration JSON path.",
    )
    suite.set_defaults(func=run_suite_command)

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
