from __future__ import annotations

import argparse
import json
from pathlib import Path

from context_auditor.bloat import summarize_traces
from context_auditor.io import load_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize audit JSONL traces.")
    parser.add_argument("trace_path")
    parser.add_argument("--out", default="results/summary.json")
    args = parser.parse_args()

    summary = summarize_traces(load_jsonl(Path(args.trace_path)))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote summary to {out}")


if __name__ == "__main__":
    main()
