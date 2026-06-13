from __future__ import annotations

import argparse

from experiments.pilot import run_pilot


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the controlled pilot experiment.")
    parser.add_argument("--out", default="traces/pilot.jsonl", help="Output JSONL trace path.")
    args = parser.parse_args()
    run_pilot(args.out)
    print(f"Wrote traces to {args.out}")


if __name__ == "__main__":
    main()
