from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from context_auditor.io import load_jsonl
from context_auditor.cli import build_parser
from experiments.langchain_pilot import run_langchain_pilot


class LangChainPilotTests(unittest.TestCase):
    def test_cli_exposes_langchain_pilot_command(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "run-langchain-pilot",
                "--config",
                "configs/langchain_pilot.json",
                "--out",
                "traces/langchain_pilot.jsonl",
            ]
        )
        self.assertEqual(args.config, "configs/langchain_pilot.json")
        self.assertEqual(args.out, "traces/langchain_pilot.jsonl")
        self.assertTrue(callable(args.func))

    def test_langchain_pilot_writes_framework_specific_traces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "langchain.jsonl"
            config = root / "config.json"
            config.write_text(
                json.dumps(
                    {
                        "experiment_id": "langchain-test-v0.7",
                        "run_id": "run-langchain-test",
                        "dataset_name": "controlled_synthetic",
                        "provider": "mock",
                        "model": "mock-llm",
                        "output_path": str(output),
                        "workflow_configs": {
                            "retrieval_qa": [
                                {
                                    "configuration": "retrieval_duplicate",
                                    "retrieval_top_k": 2,
                                    "duplicate_retrieval": True,
                                }
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )

            run_langchain_pilot(output, config)

            traces = load_jsonl(output)
            self.assertEqual(len(traces), 6)
            self.assertTrue(all(trace.framework == "langchain" for trace in traces))
            self.assertTrue(all(trace.experiment_id == "langchain-test-v0.7" for trace in traces))
            self.assertTrue(any(trace.metrics["source_ratios"].get("retrieval", 0) > 0 for trace in traces))
            final_traces = [trace for trace in traces if trace.task_success is not None]
            self.assertEqual(len(final_traces), 3)
            self.assertTrue(all(trace.task_success for trace in final_traces))


if __name__ == "__main__":
    unittest.main()
