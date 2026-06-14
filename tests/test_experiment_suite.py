from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from context_auditor.cli import build_parser
from experiments.suite import run_experiment_suite


class ExperimentSuiteTests(unittest.TestCase):
    def test_cli_exposes_run_suite_command(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "run-suite",
                "--out-dir",
                "artifacts",
                "--custom-config",
                "configs/pilot.json",
                "--langchain-config",
                "configs/langchain_pilot.json",
            ]
        )
        self.assertEqual(args.out_dir, "artifacts")
        self.assertEqual(args.custom_config, "configs/pilot.json")
        self.assertEqual(args.langchain_config, "configs/langchain_pilot.json")
        self.assertTrue(callable(args.func))

    def test_suite_runs_both_frameworks_and_writes_comparison_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            custom_config = root / "custom.json"
            langchain_config = root / "langchain.json"
            _write_minimal_config(custom_config, "custom-suite-test", "traces/ignored-custom.jsonl")
            _write_minimal_config(langchain_config, "langchain-suite-test", "traces/ignored-langchain.jsonl")

            outputs = run_experiment_suite(
                output_dir=root / "suite",
                custom_config=custom_config,
                langchain_config=langchain_config,
            )

            self.assertTrue(outputs["custom_trace_path"].exists())
            self.assertTrue(outputs["langchain_trace_path"].exists())
            self.assertTrue(outputs["custom_summary_path"].exists())
            self.assertTrue(outputs["langchain_summary_path"].exists())
            self.assertTrue(outputs["framework_comparison_json_path"].exists())
            self.assertTrue(outputs["framework_comparison_csv_path"].exists())
            self.assertTrue(outputs["custom_mitigation_json_path"].exists())
            self.assertTrue(outputs["custom_mitigation_csv_path"].exists())
            self.assertTrue(outputs["langchain_mitigation_json_path"].exists())
            self.assertTrue(outputs["langchain_mitigation_csv_path"].exists())
            self.assertTrue(outputs["manifest_path"].exists())

            comparison = json.loads(outputs["framework_comparison_json_path"].read_text(encoding="utf-8"))
            self.assertEqual(comparison["frameworks"], ["custom-react", "langchain"])
            self.assertEqual(comparison["configuration_count"], 1)
            self.assertEqual(comparison["rows"][0]["configuration"], "retrieval_top1")

            manifest = json.loads(outputs["manifest_path"].read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifact_version"], "0.9.0")
            self.assertEqual(manifest["schema_version"], "0.9.0")
            self.assertEqual(manifest["configs"]["custom"], str(custom_config))
            self.assertEqual(manifest["configs"]["langchain"], str(langchain_config))
            self.assertEqual(manifest["trace_counts"]["custom-react"], 6)
            self.assertEqual(manifest["trace_counts"]["langchain"], 6)
            self.assertEqual(manifest["framework_comparison_rows"], 1)
            self.assertIn("generated_at", manifest)


def _write_minimal_config(path: Path, experiment_id: str, output_path: str) -> None:
    path.write_text(
        json.dumps(
            {
                "experiment_id": experiment_id,
                "run_id": "run-suite-test",
                "dataset_name": "controlled_synthetic",
                "provider": "mock",
                "model": "mock-llm",
                "output_path": output_path,
                "workflow_configs": {
                    "retrieval_qa": [
                        {"configuration": "retrieval_top1", "retrieval_top_k": 1},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
