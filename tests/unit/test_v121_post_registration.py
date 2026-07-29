import csv
import json
import subprocess
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from context_auditor.application.detector_calibration import (
    apply_selected_thresholds,
    calibrate_detector,
)
from context_auditor.application.study_c_evidence import (
    build_itt_execution_table,
)
from context_auditor.cli.main import build_parser
from context_auditor.domain.models import TextSegment
from context_auditor.experiments.protocol_lock import (
    freeze_protocol_package,
    validate_protocol_registration,
)


class PostRegistrationTests(unittest.TestCase):
    def test_annotation_export_requires_explicit_split(self):
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "export-context-annotations",
                    "--bundle",
                    "bundle.zip",
                    "--output",
                    "annotations",
                    "--annotation-set-id",
                    "cal-v1",
                ]
            )

    def test_calibration_is_deterministic_and_rejects_contamination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = make_calibration_inputs(root)
            first = calibrate_detector(
                *inputs,
                root / "out-a",
                annotation_set_id="cal-v1",
            )
            second = calibrate_detector(
                *inputs,
                root / "out-b",
                annotation_set_id="cal-v1",
            )
            self.assertEqual(
                (first / "selected_thresholds.json").read_bytes(),
                (second / "selected_thresholds.json").read_bytes(),
            )
            self.assertEqual(
                (first / "threshold_selection_audit.csv").read_bytes(),
                (second / "threshold_selection_audit.csv").read_bytes(),
            )
            selected = json.loads(
                (first / "selected_thresholds.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                selected["thresholds"]["near_duplicate_threshold"],
                0.6,
            )
            contaminated = root / "contaminated.jsonl"
            item = json.loads(inputs[0].read_text(encoding="utf-8"))
            item["detected_labels"] = {}
            contaminated.write_text(
                json.dumps(item) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "forbidden"):
                calibrate_detector(
                    contaminated,
                    *inputs[1:],
                    root / "out-contaminated",
                    annotation_set_id="cal-v1",
                )
            heldout = root / "heldout.jsonl"
            item.pop("detected_labels")
            item["dataset_split"] = "test"
            heldout.write_text(json.dumps(item) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "held-out"):
                calibrate_detector(
                    heldout,
                    *inputs[1:],
                    root / "out-heldout",
                    annotation_set_id="cal-v1",
                )

            heldout_config = root / "heldout.json"
            heldout_config.write_text(
                json.dumps(
                    {
                        "schema_version": "1.2.1",
                        "dataset_split": "test",
                        "near_duplicate_threshold": 0.8,
                        "relevance_threshold": 0.05,
                        "verbose_tool_token_threshold": 80,
                        "source_dominance_threshold": 0.65,
                    }
                ),
                encoding="utf-8",
            )
            audit = apply_selected_thresholds(
                first / "selected_thresholds.json",
                [heldout_config],
                root / "threshold-application.json",
            )
            self.assertTrue(audit.is_file())
            applied = json.loads(heldout_config.read_text(encoding="utf-8"))
            self.assertEqual(applied["near_duplicate_threshold"], 0.6)

    def test_fail_closed_gate_verifies_release_package_and_runtime_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plans = root / "thesis" / "plans"
            releases = root / "thesis" / "releases"
            plans.mkdir(parents=True)
            protocol = plans / "protocol.md"
            protocol.write_text("frozen\n", encoding="utf-8")
            manifest = plans / "osf_registration_manifest_v1.2.1.json"
            manifest.write_text(
                json.dumps(
                    {
                        "protocol_version": "1.2.1",
                        "initial_required_files": ["protocol.md"],
                        "clarification_required_files": ["protocol.md"],
                        "addendum_required_files": ["protocol.md"],
                        "initial_registration": {},
                        "calibration_method_clarification": {},
                        "calibration_addendum": {},
                    }
                ),
                encoding="utf-8",
            )
            git(root, "init")
            git(root, "config", "user.email", "tests@example.invalid")
            git(root, "config", "user.name", "Test Runner")
            git(root, "add", ".")
            git(root, "commit", "-m", "base")

            initial_package = freeze_protocol_package(
                root,
                releases / "initial.zip",
                phase="initial",
            )
            git(root, "add", ".")
            git(root, "commit", "-m", "initial package")
            initial_commit = git(root, "rev-parse", "HEAD")
            git(root, "tag", "initial-release")
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["initial_registration"].update(
                {
                    "registration_status": "registered",
                    "registration_url": "https://osf.io/init1/overview",
                    "registered_at": "2026-07-29T12:58:00+03:00",
                    "github_release_tag": "initial-release",
                    "github_release_commit": initial_commit,
                    "calibration_calls_allowed": True,
                }
            )
            manifest.write_text(json.dumps(data), encoding="utf-8")
            git(root, "add", ".")
            git(root, "commit", "-m", "record initial registration")

            clarification_package = freeze_protocol_package(
                root,
                releases / "clarification.zip",
                phase="clarification",
            )
            git(root, "add", ".")
            git(root, "commit", "-m", "clarification package")
            clarification_commit = git(root, "rev-parse", "HEAD")
            git(root, "tag", "clarification-release")
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["calibration_method_clarification"].update(
                {
                    "registration_status": "registered",
                    "registration_url": "https://osf.io/clari1/overview",
                    "registered_at": "2026-07-30T10:00:00+03:00",
                    "github_release_tag": "clarification-release",
                    "github_release_commit": clarification_commit,
                    "calibration_calls_allowed": False,
                }
            )
            manifest.write_text(json.dumps(data), encoding="utf-8")
            result = validate_protocol_registration(root, phase="calibration")
            self.assertTrue(result["derived_calls_allowed"])
            self.assertEqual(len(result["evidence_chain"]), 2)
            self.assertTrue(initial_package.is_file())
            self.assertTrue(clarification_package.is_file())

            protocol.write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "runtime file changed"):
                validate_protocol_registration(root, phase="calibration")

    def test_itt_retains_failed_dispatch_without_trace_or_human_rating(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "ledger.jsonl"
            records = [
                {
                    "event": "reserved",
                    "call_id": "call-0001",
                    "call_index": 1,
                    "cell_id": "cell-a",
                    "task_id": "task-a",
                    "framework": "langchain",
                    "arm": "provenance_aware",
                    "invocation_index": 0,
                    "status": "reserved",
                    "retry_of": None,
                },
                {
                    "event": "failed",
                    "call_id": "call-0001",
                    "call_index": 1,
                    "cell_id": "cell-a",
                    "task_id": "task-a",
                    "framework": "langchain",
                    "arm": "provenance_aware",
                    "invocation_index": 0,
                    "status": "failed",
                    "error_type": "TimeoutError",
                    "retry_of": None,
                },
            ]
            ledger.write_text(
                "\n".join(json.dumps(item) for item in records) + "\n",
                encoding="utf-8",
            )
            rows = build_itt_execution_table(ledger, [], {})
            self.assertEqual(len(rows), 1)
            self.assertFalse(rows[0]["itt_task_success"])
            self.assertEqual(rows[0]["failure_reason"], "TimeoutError")


def make_calibration_inputs(root: Path) -> tuple[Path, Path, Path, Path, Path]:
    segment_a = TextSegment(
        segment_id="seg-a",
        parent_message_id="msg-a",
        message_index=0,
        ordinal=0,
        role="system",
        source_type="retrieval",
        text="alpha beta gamma delta",
        char_count=22,
        token_count=4,
        content_hash="a" * 64,
        normalized_hash="b" * 64,
        privacy_mode="redacted",
    )
    segment_b = TextSegment(
        segment_id="seg-b",
        parent_message_id="msg-b",
        message_index=1,
        ordinal=0,
        role="system",
        source_type="retrieval",
        text="alpha beta gamma epsilon",
        char_count=24,
        token_count=4,
        content_hash="c" * 64,
        normalized_hash="d" * 64,
        privacy_mode="redacted",
    )
    context = root / "contexts.jsonl"
    context.write_text(
        json.dumps(
            {
                "schema_version": "1.2.1",
                "trace_id": "trace-a",
                "task_id": "task-a",
                "framework": "langchain",
                "workflow_family": "retrieval_qa",
                "dataset_split": "calibration",
                "query": "alpha beta",
                "segments": [asdict(segment_a), asdict(segment_b)],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    linkage = root / "annotation_linkage.csv"
    linkage_fields = (
        "sample_id",
        "segment_key",
        "trace_id",
        "task_id",
        "framework",
        "workflow_family",
        "segment_id",
        "source_type",
        "token_count",
    )
    linkage_rows = [
        {
            "sample_id": "sample-a",
            "segment_key": "key-a",
            "trace_id": "trace-a",
            "task_id": "task-a",
            "framework": "langchain",
            "workflow_family": "retrieval_qa",
            "segment_id": "seg-a",
            "source_type": "retrieval",
            "token_count": "4",
        },
        {
            "sample_id": "sample-a",
            "segment_key": "key-b",
            "trace_id": "trace-a",
            "task_id": "task-a",
            "framework": "langchain",
            "workflow_family": "retrieval_qa",
            "segment_id": "seg-b",
            "source_type": "retrieval",
            "token_count": "4",
        },
    ]
    write_rows(linkage, linkage_fields, linkage_rows)
    raw_fields = ("segment_key", "decision")
    raw_rows = [
        {"segment_key": "key-a", "decision": "keep"},
        {"segment_key": "key-b", "decision": "remove"},
    ]
    reviewer_a = root / "reviewer-a.csv"
    reviewer_b = root / "reviewer-b.csv"
    write_rows(reviewer_a, raw_fields, raw_rows)
    write_rows(reviewer_b, raw_fields, raw_rows)
    adjudication = root / "adjudication.csv"
    write_rows(
        adjudication,
        (
            "segment_key",
            "adjudicated_decision",
            "adjudicated_reasons",
        ),
        [
            {
                "segment_key": "key-a",
                "adjudicated_decision": "keep",
                "adjudicated_reasons": "",
            },
            {
                "segment_key": "key-b",
                "adjudicated_decision": "remove",
                "adjudicated_reasons": "near_duplicate",
            },
        ],
    )
    return context, reviewer_a, reviewer_b, adjudication, linkage


def write_rows(path: Path, fields, rows) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
