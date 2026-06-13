from __future__ import annotations

import argparse

from experiments.pilot import run_pilot


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the controlled pilot experiment.")
    parser.add_argument("--out", default="traces/pilot.jsonl", help="Output JSONL trace path.")
    parser.add_argument("--config", default="configs/pilot.json", help="Experiment configuration JSON path.")
    args = parser.parse_args()
    run_pilot(args.out, args.config)
    print(f"Wrote traces to {args.out}")


if __name__ == "__main__":
    main()
