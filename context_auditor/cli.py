"""Command-line interface for the context bloat auditor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ._version import __version__
from .bloat import summarize_traces
from .io import load_jsonl
from .mitigation import remove_exact_duplicate_segments


def run_pilot_command(args: argparse.Namespace) -> None:
    from experiments.pilot import run_pilot

    run_pilot(args.out)
    print(f"Wrote traces to {args.out}")


def analyze_command(args: argparse.Namespace) -> None:
    traces = load_jsonl(args.trace_path)
    summary = summarize_traces(traces)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote summary to {output}")


def mitigate_command(args: argparse.Namespace) -> None:
    traces = load_jsonl(args.trace_path)
    reports = []
    for trace in traces:
        _, report = remove_exact_duplicate_segments(trace)
        reports.append(
            {
                "trace_id": trace.trace_id,
                "task_id": trace.task_id,
                "configuration": trace.configuration,
                **report.to_dict(),
            }
        )

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote mitigation report to {output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="context-auditor")
    parser.add_argument("--version", action="version", version=f"context-auditor {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    pilot = subparsers.add_parser("run-pilot", help="Run controlled pilot experiments.")
    pilot.add_argument("--out", default="traces/pilot.jsonl", help="Output JSONL trace path.")
    pilot.set_defaults(func=run_pilot_command)

    analyze = subparsers.add_parser("analyze", help="Summarize a JSONL trace file.")
    analyze.add_argument("trace_path")
    analyze.add_argument("--out", default="results/summary.json")
    analyze.set_defaults(func=analyze_command)

    mitigate = subparsers.add_parser("mitigate", help="Report exact duplicate segment mitigation.")
    mitigate.add_argument("trace_path")
    mitigate.add_argument("--out", default="results/mitigation_report.json")
    mitigate.set_defaults(func=mitigate_command)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

