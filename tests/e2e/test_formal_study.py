import json
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from context_auditor.application.study_bundle import (
    ExportStudyBundle,
    validate_study_bundle,
)
from context_auditor.application.annotations import export_blind_review_package
from context_auditor.experiments import RunFormalExperiment, load_experiment_config
from context_auditor.experiments.dataset_validation import validate_dataset


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FormalStudyTests(unittest.TestCase):
    def test_benchmark_has_frozen_split_and_workflow_counts(self):
        dataset_root = (
            PROJECT_ROOT / "data" / "datasets" / "context_bloat_benchmark" / "v1"
        )
        data = {
            "tasks": json.loads((dataset_root / "tasks.json").read_text("utf-8")),
            "documents": json.loads(
                (dataset_root / "documents.json").read_text("utf-8")
            ),
            "memory": json.loads((dataset_root / "memory.json").read_text("utf-8")),
            "manifest": json.loads(
                (dataset_root / "dataset_manifest.json").read_text("utf-8")
            ),
        }

        result = validate_dataset(data)

        self.assertEqual(result["task_count"], 36)
        self.assertEqual(result["split_counts"], {"calibration": 6, "test": 30})
        self.assertEqual(
            result["workflow_counts"],
            {
                "memory_turns": 12,
                "multi_step_tool": 12,
                "retrieval_qa": 12,
            },
        )

    def test_stress_suite_exports_a_valid_cohort_separated_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(PROJECT_ROOT / "data", root / "data")
            shutil.copytree(
                PROJECT_ROOT / "configs" / "conclusions",
                root / "configs" / "conclusions",
            )
            run_paths = []
            for filename in (
                "formal_full_mock_custom_react_v1.json",
                "formal_full_mock_langchain_v1.json",
            ):
                loaded = load_experiment_config(
                    PROJECT_ROOT / "configs" / "experiments" / filename
                )
                config = replace(
                    loaded,
                    experiment_id=f"test-{loaded.experiment_id}",
                    repetitions=2,
                    task_ids=(
                        "retrieval-test-001",
                        "retrieval-test-002",
                        "memory-test-001",
                        "memory-test-002",
                        "tool-test-001",
                        "tool-test-002",
                    ),
                )
                run_paths.append(RunFormalExperiment(root).execute(config))

            bundle = ExportStudyBundle(root).execute(
                run_paths,
                root / "runs" / "studies" / "stress.zip",
            )
            result = validate_study_bundle(bundle)
            annotations = export_blind_review_package(
                bundle,
                root / "annotations",
            )
            annotation_manifest = json.loads(
                (annotations / "annotation_manifest.json").read_text("utf-8")
            )

            self.assertTrue(result["valid"])
            self.assertEqual(result["trace_count"], 184)
            self.assertEqual(result["task_count"], 6)
            self.assertEqual(annotation_manifest["stratum_count"], 36)
            self.assertEqual(annotation_manifest["reviewer_a_count"], 72)
            self.assertEqual(annotation_manifest["reviewer_b_count"], 36)


if __name__ == "__main__":
    unittest.main()
