import json
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from context_auditor.adapters.providers import MockProvider
from context_auditor.application.study_bundle import ExportStudyBundle
from context_auditor.experiments import (
    RunExternalValidation,
    load_external_validation_config,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ExternalValidationE2ETests(unittest.TestCase):
    def test_mock_external_run_writes_natural_v12_traces(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_project(root)
            loaded = load_external_validation_config(
                PROJECT_ROOT
                / "configs"
                / "experiments"
                / "external_calibration_custom_react_v1.2.json"
            )
            config = replace(
                loaded,
                source_path=(
                    PROJECT_ROOT
                    / "configs"
                    / "experiments"
                    / "external_calibration_custom_react_v1.2.json"
                ),
            )
            run = RunExternalValidation(root, MockProvider()).execute(config)
            lines = (
                run / "traces" / "invocations.jsonl"
            ).read_text(encoding="utf-8").splitlines()
            traces = [json.loads(line) for line in lines]
            self.assertEqual(len(traces), 4)
            self.assertEqual(
                sum(item["task_success"] is not None for item in traces),
                3,
            )
            self.assertTrue(all(item["schema_version"] == "1.2.0" for item in traces))
            self.assertTrue(all(item["evidence_tier"] == "natural" for item in traces))
            self.assertTrue(
                all(not item["injected_labels"] for item in traces)
            )
            self.assertTrue(
                all(item["provider_payload_hash"] for item in traces)
            )
            bundle = ExportStudyBundle(root).execute(
                [run],
                root / "runs" / "studies" / "external.zip",
            )
            self.assertTrue(bundle.is_file())


def make_project(root: Path) -> None:
    dataset = root / "data" / "datasets" / "external_validation" / "v1"
    dataset.mkdir(parents=True)
    tasks = [
        {
            "task_id": "hotpot-cal-1",
            "source_dataset": "hotpotqa",
            "source_record_id": "1",
            "workflow_family": "retrieval_qa",
            "split": "calibration",
            "prompt": "What color is the sky?",
            "expected_answer": "blue",
            "scoring": {"type": "contains"},
            "documents": [
                {"source_id": "d1", "title": "Sky", "text": "The sky is blue."}
            ],
        },
        {
            "task_id": "longmem-cal-1",
            "source_dataset": "longmemeval",
            "source_record_id": "2",
            "workflow_family": "memory_turns",
            "split": "calibration",
            "prompt": "What drink was preferred?",
            "expected_answer": "tea",
            "scoring": {"type": "contains"},
            "memory_sessions": [
                {"source_id": "m1", "date": "2026-01-01", "text": "user: I prefer tea."}
            ],
        },
        {
            "task_id": "bfcl-cal-1",
            "source_dataset": "bfcl-v3",
            "source_record_id": "3",
            "workflow_family": "multi_step_tool",
            "split": "calibration",
            "prompt": "Add one and two.",
            "expected_answer": "[]",
            "scoring": {"type": "tool_call"},
            "tools": [
                {
                    "name": "add",
                    "description": "Add values",
                    "parameters": {"type": "object"},
                }
            ],
            "expected_tool_calls": [{"name": "add", "arguments": {"a": 1, "b": 2}}],
        },
    ]
    (dataset / "tasks.json").write_text(
        json.dumps(tasks),
        encoding="utf-8",
    )
    (dataset / "dataset_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.2.0",
                "dataset_name": "external_validation",
                "dataset_version": "v1",
            }
        ),
        encoding="utf-8",
    )
    shutil.copytree(
        PROJECT_ROOT / "configs" / "conclusions",
        root / "configs" / "conclusions",
    )


if __name__ == "__main__":
    unittest.main()
