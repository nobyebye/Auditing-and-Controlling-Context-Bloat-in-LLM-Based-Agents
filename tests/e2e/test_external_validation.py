import json
import shutil
import tempfile
import unittest
import csv
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from context_auditor.adapters.providers import (
    DeterministicCompressionBackend,
    LLMLingua2Compressor,
    MockProvider,
)
from context_auditor.application.external_annotations import (
    adjudicate_annotation_files,
    export_context_annotation_packages,
)
from context_auditor.application.external_evidence import BuildExternalEvidence
from context_auditor.application.outcome_annotations import (
    adjudicate_outcome_files,
    export_outcome_annotation_packages,
)
from context_auditor.application.study_c_evidence import build_study_c_evidence
from context_auditor.application.study_bundle import ExportStudyBundle
from context_auditor.experiments import (
    RunExternalValidation,
    load_external_validation_config,
)
from context_auditor.experiments.study_c import (
    RunStudyC,
    load_study_c_config,
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
                / "external_calibration_custom_react_v1.2.1.json"
            )
            config = replace(
                loaded,
                provider="mock",
                model="mock-v1",
                source_path=(
                    PROJECT_ROOT
                    / "configs"
                    / "experiments"
                    / "external_calibration_custom_react_v1.2.1.json"
                ),
            )
            run = RunExternalValidation(
                root,
                MockProvider("mock-v1"),
            ).execute(config)
            lines = (
                run / "traces" / "invocations.jsonl"
            ).read_text(encoding="utf-8").splitlines()
            traces = [json.loads(line) for line in lines]
            self.assertEqual(len(traces), 16)
            self.assertEqual(
                sum(item["task_success"] is not None for item in traces),
                12,
            )
            self.assertTrue(all(item["schema_version"] == "1.2.1" for item in traces))
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

    def test_full_mock_study_b_c_pipeline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_project(root)
            runs = []
            for filename in (
                "external_test_mock_custom_react_v1.2.1.json",
                "external_test_mock_langchain_v1.2.1.json",
            ):
                config = load_external_validation_config(
                    PROJECT_ROOT / "configs" / "experiments" / filename
                )
                runs.append(
                    RunExternalValidation(
                        root,
                        MockProvider(config.model),
                    ).execute(config)
                )
            bundle = ExportStudyBundle(root).execute(
                runs,
                root / "runs" / "studies" / "mock-study-b.zip",
            )
            with patch(
                "context_auditor.experiments.protocol_lock."
                "validate_protocol_registration",
                return_value={"valid": True},
            ):
                package = export_context_annotation_packages(
                    bundle,
                    root / "annotations" / "study-b",
                    project_root=root,
                    annotation_set_id="mock-study-b-v1",
                    include_split="test",
                )
            complete_mock_segment_reviews(package / "reviewer_a.csv")
            complete_mock_segment_reviews(package / "reviewer_b.csv")
            adjudication = adjudicate_annotation_files(
                package / "reviewer_a.csv",
                package / "reviewer_b.csv",
                package / "annotation_linkage.csv",
                root / "annotations" / "study-b-consensus",
                annotation_set_id="mock-study-b-v1",
            )
            evidence = BuildExternalEvidence(root).execute(
                bundle,
                adjudication / "adjudication.csv",
                package / "annotation_linkage.csv",
                root / "evidence" / "study-b",
                annotation_set_id="mock-study-b-v1",
            )
            self.assertTrue((evidence / "rq_evidence.json").is_file())
            study_c_config = load_study_c_config(
                PROJECT_ROOT
                / "configs"
                / "experiments"
                / "study_c_mock_v1.2.1.json"
            )
            compressor = LLMLingua2Compressor(
                backend=DeterministicCompressionBackend(),
            )
            study_c_run = RunStudyC(
                root,
                MockProvider(study_c_config.model),
                compressor,
            ).execute(
                study_c_config,
                bundle_path=bundle,
                adjudication_path=adjudication / "adjudication.csv",
                annotation_linkage_path=package / "annotation_linkage.csv",
                annotation_set_id="mock-study-b-v1",
            )
            summary = json.loads(
                (study_c_run / "reports" / "summary.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(summary["mitigation_trace_count"], 180)
            self.assertLessEqual(summary["counterfactual_trace_count"], 108)
            self.assertTrue(summary["budget_preflight_passed"])
            outcomes = export_outcome_annotation_packages(
                study_c_run / "traces" / "invocations.jsonl",
                root / "annotations" / "study-c",
                annotation_set_id="mock-study-c-v1",
            )
            complete_mock_outcome_reviews(outcomes / "reviewer_a.csv")
            complete_mock_outcome_reviews(outcomes / "reviewer_b.csv")
            outcome_adjudication = adjudicate_outcome_files(
                outcomes / "reviewer_a.csv",
                outcomes / "reviewer_b.csv",
                outcomes / "answer_key.csv",
                root / "annotations" / "study-c-consensus",
                annotation_set_id="mock-study-c-v1",
            )
            study_c_evidence = build_study_c_evidence(
                study_c_run / "traces" / "invocations.jsonl",
                (
                    root
                    / "runs"
                    / "studies"
                    / "external-validation-v1.2.1-mock-ledger.jsonl"
                ),
                outcome_adjudication / "adjudication.csv",
                outcomes / "answer_key.csv",
                root / "evidence" / "study-c",
            )
            self.assertTrue(
                (study_c_evidence / "study_c_evidence.json").is_file()
            )
            ledger = (
                root
                / "runs"
                / "studies"
                / "external-validation-v1.2.1-mock-ledger.jsonl"
            )
            reservations = [
                json.loads(line)
                for line in ledger.read_text(encoding="utf-8").splitlines()
                if json.loads(line).get("event") == "reserved"
            ]
            self.assertLessEqual(len(reservations), 500)


def make_project(root: Path) -> None:
    dataset = root / "data" / "datasets" / "external_validation" / "v1"
    shutil.copytree(
        PROJECT_ROOT / "data" / "datasets" / "external_validation" / "v1",
        dataset,
    )
    shutil.copytree(
        PROJECT_ROOT / "configs" / "conclusions",
        root / "configs" / "conclusions",
    )


def complete_mock_segment_reviews(path: Path) -> None:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = tuple(rows[0])
    seen: dict[str, int] = {}
    for row in rows:
        position = seen.get(row["sample_id"], 0)
        row["decision"] = "remove" if position == 0 else "keep"
        row["reasons"] = "other" if position == 0 else ""
        row["confidence_1_to_5"] = "5"
        row["block_started_at"] = "2026-07-27T10:00:00Z"
        row["block_completed_at"] = "2026-07-27T10:10:00Z"
        seen[row["sample_id"]] = position + 1
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def complete_mock_outcome_reviews(path: Path) -> None:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = tuple(rows[0])
    for row in rows:
        row["decision"] = "success"
        row["confidence_1_to_5"] = "5"
        row["block_started_at"] = "2026-07-27T10:00:00Z"
        row["block_completed_at"] = "2026-07-27T10:10:00Z"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
