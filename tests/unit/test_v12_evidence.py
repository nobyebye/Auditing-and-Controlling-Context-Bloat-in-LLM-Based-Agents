import csv
import json
import tempfile
import unittest
import zipfile
import subprocess
from dataclasses import replace
from pathlib import Path

from context_auditor.adapters.common import DefaultIdGenerator, RegexTokenizer, UtcClock
from context_auditor.adapters.providers import LLMLingua2Compressor
from context_auditor.adapters.storage import JsonlTraceRepository
from context_auditor.adapters.storage.jsonl import trace_from_dict
from context_auditor.application.agreement import annotation_agreement
from context_auditor.application.call_budget import PersistentCallBudget
from context_auditor.application.capture import CaptureContext
from context_auditor.application.counterfactual import build_counterfactual_variant
from context_auditor.application.external_annotations import (
    import_context_annotation_file,
)
from context_auditor.application.external_statistics import (
    build_study_b_statistics,
    compare_source_rankings,
)
from context_auditor.application.segmentation import segment_messages
from context_auditor.application.study_c_evidence import (
    evaluate_mitigation_arms,
)
from context_auditor.domain.enums import PrivacyMode
from context_auditor.domain.models import (
    AuditTrace,
    CaptureRequest,
    Message,
    ModelRequestEnvelope,
    ProviderRequestRecord,
    ProviderUsage,
    ReferenceAnnotation,
    TextSegment,
)
from context_auditor.experiments.external_workflow import canonical_tool_calls
from context_auditor.experiments.external_dataset import sanitize_external_task
from context_auditor.experiments.protocol_lock import (
    freeze_protocol_package,
    validate_protocol_registration,
)


class V12EvidenceTests(unittest.TestCase):
    def test_natural_capture_rejects_injected_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture = CaptureContext(
                JsonlTraceRepository(Path(temporary) / "trace.jsonl"),
                RegexTokenizer(),
                UtcClock(),
                DefaultIdGenerator(),
            )
            with self.assertRaises(ValueError):
                capture.execute(
                    make_capture_request(
                        (
                            Message(
                                "system",
                                "duplicate",
                                metadata={"bloat_labels": ["exact_duplicate"]},
                            ),
                        ),
                        evidence_tier="natural",
                    )
                )

    def test_payload_mismatch_is_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture = CaptureContext(
                JsonlTraceRepository(Path(temporary) / "trace.jsonl"),
                RegexTokenizer(),
                UtcClock(),
                DefaultIdGenerator(),
            )
            request = make_capture_request(
                (Message("user", "hello"),),
                evidence_tier="natural",
            )
            request = CaptureRequest(
                **{
                    **request.__dict__,
                    "framework_capture_hash": "a" * 64,
                    "provider_request": ProviderRequestRecord(
                        endpoint="mock://test",
                        method="POST",
                        sent_at="2026-01-01T00:00:00Z",
                        payload_sha256="b" * 64,
                        redacted_payload={},
                    ),
                }
            )
            trace = capture.execute(request)
            self.assertIn("payload_mismatch", trace.risk_flags)

    def test_v11_trace_is_mapped_to_injected_labels(self):
        data = {
            "schema_version": "1.1.0",
            "trace_id": "t",
            "timestamp": "2026-01-01T00:00:00Z",
            "experiment_id": "e",
            "run_id": "r",
            "task_id": "task",
            "framework": "custom-react",
            "provider": "mock",
            "model": "mock",
            "configuration": "c",
            "workflow_family": "retrieval_qa",
            "dataset_name": "d",
            "dataset_version": "v1",
            "repetition_id": 0,
            "seed": 1,
            "invocation_index": 0,
            "config_hash": "h",
            "privacy_mode": "redacted",
            "messages": [],
            "segments": [],
            "metrics": {},
            "ground_truth_labels": {"s1": ["exact_duplicate"]},
        }
        trace = trace_from_dict(data)
        self.assertEqual(
            trace.injected_labels,
            {"s1": ("exact_duplicate",)},
        )

    def test_annotation_agreement_reports_all_statistics(self):
        left = [
            {"segment_key": "a", "decision": "keep", "reasons": ""},
            {"segment_key": "b", "decision": "remove", "reasons": "exact_duplicate"},
        ]
        right = [
            {"segment_key": "a", "decision": "keep", "reasons": ""},
            {"segment_key": "b", "decision": "remove", "reasons": "exact_duplicate"},
        ]
        result = annotation_agreement(left, right)
        self.assertEqual(result["percent_agreement"], 1.0)
        self.assertEqual(result["cohen_kappa"], 1.0)
        self.assertEqual(result["gwet_ac1"], 1.0)

    def test_context_annotation_import_freezes_complete_blinded_form(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reviewer = root / "reviewer.csv"
            answer_key = root / "answer_key.csv"
            fields = (
                "sample_id",
                "segment_key",
                "task_prompt",
                "message_index",
                "role",
                "segment_ordinal",
                "segment_text",
                "decision",
                "reasons",
                "confidence_1_to_5",
                "notes",
            )
            with reviewer.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow(
                    {
                        "sample_id": "sample",
                        "segment_key": "segment",
                        "task_prompt": "question",
                        "message_index": "0",
                        "role": "system",
                        "segment_ordinal": "0",
                        "segment_text": "context",
                        "decision": "remove",
                        "reasons": "exact_duplicate",
                        "confidence_1_to_5": "5",
                        "notes": "",
                    }
                )
            with answer_key.open(
                "w", encoding="utf-8-sig", newline=""
            ) as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=(
                        "sample_id",
                        "segment_key",
                        "trace_id",
                        "segment_id",
                    ),
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "sample_id": "sample",
                        "segment_key": "segment",
                        "trace_id": "trace",
                        "segment_id": "s1",
                    }
                )
            output = import_context_annotation_file(
                reviewer,
                answer_key,
                root / "imported",
                annotation_set_id="annotations-v1",
                reviewer_id="reviewer-a",
            )
            manifest = json.loads(
                (output / "import_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["annotation_count"], 1)
            self.assertTrue(manifest["validation"]["complete_coverage"])

    def test_counterfactual_removes_only_managed_segment(self):
        trace = make_counterfactual_trace()
        variant = build_counterfactual_variant(
            trace,
            ("s1",),
            variant_type="remove_human_candidate",
        )
        self.assertEqual(
            [message.content for message in variant.request.messages],
            ["question"],
        )
        with self.assertRaises(ValueError):
            build_counterfactual_variant(
                trace,
                ("s2",),
                variant_type="invalid",
            )

    def test_persistent_call_budget_refuses_call_501(self):
        with tempfile.TemporaryDirectory() as temporary:
            budget = PersistentCallBudget(
                Path(temporary) / "ledger.jsonl",
                limit=2,
                primary_limit=2,
            )
            request = ModelRequestEnvelope(
                messages=(Message("user", "question"),),
                metadata={
                    "cell_id": "cell",
                    "task_id": "task",
                    "framework": "custom-react",
                    "arm": "unmodified",
                    "provider_invocation_index": 0,
                },
            )
            self.assertEqual(budget.reserve(request).call_index, 1)
            self.assertEqual(budget.reserve(request).call_index, 2)
            with self.assertRaises(RuntimeError):
                budget.reserve(request)

    def test_manual_retries_are_single_use_and_ledger_ordered(self):
        with tempfile.TemporaryDirectory() as temporary:
            budget = PersistentCallBudget(
                Path(temporary) / "ledger.jsonl",
                limit=6,
                primary_limit=4,
                retry_limit=2,
            )
            request = ModelRequestEnvelope(
                messages=(Message("user", "question"),),
                metadata={
                    "cell_id": "cell-1",
                    "task_id": "task-1",
                    "framework": "custom-react",
                    "arm": "unmodified",
                    "provider_invocation_index": 0,
                },
            )
            first = budget.reserve(request)
            budget.fail(first, TimeoutError("timed out"))
            second_request = ModelRequestEnvelope(
                messages=(Message("user", "question two"),),
                metadata={
                    **request.metadata,
                    "cell_id": "cell-2",
                    "task_id": "task-2",
                },
            )
            second = budget.reserve(second_request)
            budget.fail(second, TimeoutError("timed out"))
            out_of_order = ModelRequestEnvelope(
                messages=second_request.messages,
                metadata={**second_request.metadata, "retry_of": second.call_id},
            )
            with self.assertRaises(ValueError):
                budget.reserve(out_of_order)
            first_retry = ModelRequestEnvelope(
                messages=request.messages,
                metadata={**request.metadata, "retry_of": first.call_id},
            )
            retry = budget.reserve(first_retry)
            budget.fail(retry, TimeoutError("timed out again"))
            with self.assertRaises(ValueError):
                budget.reserve(first_retry)
            self.assertEqual(
                [item["call_id"] for item in budget.retryable_failures()],
                [second.call_id],
            )

    def test_protocol_freeze_keeps_paid_calls_blocked_until_registration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plans = root / "thesis" / "plans"
            releases = root / "thesis" / "releases"
            plans.mkdir(parents=True)
            frozen_input = plans / "protocol.md"
            frozen_input.write_text("frozen protocol\n", encoding="utf-8")
            manifest_path = plans / "osf_registration_manifest_v1.2.1.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "protocol_version": "1.2.1",
                        "registered_commit": "",
                        "initial_required_files": ["protocol.md"],
                        "clarification_required_files": ["protocol.md"],
                        "addendum_required_files": ["protocol.md"],
                        "initial_registration": {
                            "registration_status": "not_registered",
                            "registration_url": "",
                            "registered_at": "",
                            "calibration_calls_allowed": False,
                            "file_sha256": {},
                        },
                        "calibration_method_clarification": {
                            "registration_status": "not_registered",
                            "registration_url": "",
                            "registered_at": "",
                            "calibration_calls_allowed": False,
                            "file_sha256": {},
                        },
                        "calibration_addendum": {
                            "registration_status": "not_registered",
                            "registration_url": "",
                            "registered_at": "",
                            "heldout_calls_allowed": False,
                            "file_sha256": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "tests@example.invalid"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test Runner"],
                cwd=root,
                check=True,
            )
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "-m", "initial"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            package = freeze_protocol_package(
                root,
                releases / "protocol.zip",
                phase="calibration",
            )
            self.assertTrue(package.is_file())
            frozen = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                frozen["initial_registration"]["registration_status"],
                "ready_for_registration",
            )
            self.assertFalse(
                frozen["initial_registration"]["calibration_calls_allowed"]
            )
            with zipfile.ZipFile(package) as archive:
                packaged_manifest = json.loads(
                    archive.read("registration_manifest.json")
                )
            packaged_block = packaged_manifest["initial_registration"]
            self.assertEqual(
                packaged_block["protocol_package"],
                "thesis/releases/protocol.zip",
            )
            self.assertEqual(
                packaged_block["protocol_package_sha256"],
                "",
            )
            with self.assertRaises(RuntimeError):
                validate_protocol_registration(root, phase="calibration")

            self.assertEqual(
                frozen["initial_registration"]["github_release_tag"],
                "",
            )

    def test_llmlingua_preserves_control_messages(self):
        class Backend:
            def compress_prompt_llmlingua2(self, context, target_token):
                return {"compressed_prompt": "compressed retrieval"}

        messages = (
            Message("system", "keep system"),
            Message(
                "system",
                "long retrieval content",
                metadata={"source_type": "retrieval"},
            ),
            Message("user", "keep user"),
        )
        compressed = LLMLingua2Compressor(backend=Backend()).compress(
            messages,
            target_tokens=1,
        )
        self.assertEqual(compressed.messages[0].content, "keep system")
        self.assertEqual(
            compressed.messages[1].content,
            "compressed retrieval",
        )
        self.assertEqual(compressed.messages[2].content, "keep user")

    def test_bfcl_python_style_calls_are_parsed(self):
        self.assertEqual(
            canonical_tool_calls(
                [["cd(folder='document')", "sort('final_report.pdf')"]]
            ),
            [
                {"name": "cd", "arguments": {"folder": "document"}},
                {"name": "sort", "arguments": {"arg0": "final_report.pdf"}},
            ],
        )
        self.assertEqual(
            canonical_tool_calls(
                ["sort('final_report.pdf')"],
                parameter_names={"sort": ("file_name",)},
            ),
            [
                {
                    "name": "sort",
                    "arguments": {"file_name": "final_report.pdf"},
                }
            ],
        )

    def test_provenance_source_id_keeps_document_atomic(self):
        segments = segment_messages(
            (
                Message(
                    "system",
                    "title\nline one\nline two",
                    metadata={
                        "source_type": "memory",
                        "source_id": "session-1",
                    },
                ),
            ),
            RegexTokenizer(),
            PrivacyMode.REDACTED,
        )
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].source_id, "session-1")

    def test_external_dataset_sanitizes_credentials_and_emails(self):
        task = sanitize_external_task(
            {
                "prompt": "api_key=secret-value",
                "memory_sessions": [
                    {"text": "Authorization: token user@example.com"}
                ],
            }
        )
        rendered = json.dumps(task)
        self.assertNotIn("secret-value", rendered)
        self.assertNotIn("user@example.com", rendered)
        self.assertIn("[REDACTED]", rendered)

    def test_study_b_statistics_keep_uncertain_and_token_sources_prespecified(self):
        traces = [
            make_study_b_trace(
                "task-1",
                "custom-react",
                remove_tokens=3,
                keep_tokens=1,
                uncertain_tokens=2,
            ),
            make_study_b_trace(
                "task-1",
                "langchain",
                remove_tokens=2,
                keep_tokens=4,
                uncertain_tokens=0,
            ),
            make_study_b_trace(
                "task-2",
                "custom-react",
                remove_tokens=1,
                keep_tokens=9,
                uncertain_tokens=0,
            ),
        ]
        result = build_study_b_statistics(traces)
        primary = result["by_policy"]["primary"]
        sensitivity = result["by_policy"]["uncertain_as_remove"]
        source = primary["rq3_source_patterns"]["ranking"][0]
        self.assertEqual(source["source"], "retrieval")
        self.assertAlmostEqual(
            source["human_reference_bloat_token_ratio"],
            6 / 20,
        )
        self.assertAlmostEqual(
            sensitivity["rq3_source_patterns"]["ranking"][0][
                "human_reference_bloat_token_ratio"
            ],
            8 / 22,
        )

    def test_kendall_tau_b_compares_only_common_source_rankings(self):
        result = compare_source_rankings(
            {"tool": 0.5, "retrieval": 0.48, "memory": 0.46},
            [
                {
                    "source": "tool",
                    "human_reference_bloat_token_ratio": 0.4,
                },
                {
                    "source": "retrieval",
                    "human_reference_bloat_token_ratio": 0.3,
                },
                {
                    "source": "memory",
                    "human_reference_bloat_token_ratio": 0.2,
                },
                {
                    "source": "framework",
                    "human_reference_bloat_token_ratio": 0.1,
                },
            ],
        )
        self.assertEqual(result["common_source_count"], 3)
        self.assertEqual(result["kendall_tau_b"], 1.0)

    def test_missing_cost_and_latency_remain_unavailable(self):
        traces = []
        outcomes = {}
        for arm in (
            "unmodified",
            "provenance_aware",
            "llmlingua2_budget_matched",
        ):
            trace = replace(
                make_counterfactual_trace(),
                trace_id=f"trace-{arm}",
                configuration=arm,
                evidence_tier="mitigation",
                task_success=True,
                metrics={"total_tokens": 10},
                provider_usage=ProviderUsage(
                    input_tokens=10,
                    output_tokens=1,
                    total_tokens=11,
                    cost_usd=None,
                ),
                latency_ms=None,
            )
            traces.append(trace)
            outcomes[trace.trace_id] = True
        result = evaluate_mitigation_arms(traces, outcomes)
        self.assertIsNone(result["by_arm"]["unmodified"]["mean_cost_usd"])
        self.assertIsNone(result["by_arm"]["unmodified"]["mean_latency_ms"])
        comparison = result["versus_unmodified"]["provenance_aware"]
        self.assertIsNone(comparison["mean_cost_reduction_usd"])
        self.assertIsNone(comparison["mean_latency_reduction_ms"])
        self.assertEqual(comparison["cost_task_count"], 0)
        self.assertEqual(comparison["latency_task_count"], 0)


def make_capture_request(
    messages: tuple[Message, ...],
    *,
    evidence_tier: str,
) -> CaptureRequest:
    return CaptureRequest(
        experiment_id="test",
        run_id="20260727T120000Z__custom-react__mock__v1__05bd18f",
        task_id="task",
        framework="custom-react",
        provider="mock",
        model="mock",
        configuration="baseline",
        workflow_family="retrieval_qa",
        dataset_name="external_validation",
        dataset_version="v1",
        repetition_id=0,
        seed=1,
        invocation_index=0,
        messages=messages,
        request_envelope=ModelRequestEnvelope(messages),
        config_hash="abc",
        evidence_tier=evidence_tier,
    )


def make_counterfactual_trace() -> AuditTrace:
    messages = (
        Message("system", "retrieval", metadata={"source_type": "retrieval"}),
        Message("user", "question"),
    )
    segments = (
        TextSegment(
            segment_id="s1",
            parent_message_id="m0000",
            message_index=0,
            ordinal=0,
            role="system",
            source_type="retrieval",
            text="retrieval",
            char_count=9,
            token_count=1,
            content_hash="h1",
            normalized_hash="h1",
            privacy_mode="full",
        ),
        TextSegment(
            segment_id="s2",
            parent_message_id="m0001",
            message_index=1,
            ordinal=0,
            role="user",
            source_type="user",
            text="question",
            char_count=8,
            token_count=1,
            content_hash="h2",
            normalized_hash="h2",
            privacy_mode="full",
        ),
    )
    return AuditTrace(
        schema_version="1.2.0",
        trace_id="trace",
        timestamp="2026-01-01T00:00:00Z",
        experiment_id="e",
        run_id="r",
        task_id="task",
        framework="custom-react",
        provider="mock",
        model="mock",
        configuration="natural",
        workflow_family="retrieval_qa",
        dataset_name="external_validation",
        dataset_version="v1",
        repetition_id=0,
        seed=1,
        invocation_index=0,
        config_hash="h",
        privacy_mode="full",
        messages=messages,
        segments=segments,
        metrics={},
        request_envelope=ModelRequestEnvelope(messages),
        evidence_tier="natural",
        reference_annotations=(
            ReferenceAnnotation(
                segment_id="s1",
                annotator_id="consensus",
                decision="remove",
                adjudicated=True,
            ),
        ),
    )


def make_study_b_trace(
    task_id: str,
    framework: str,
    *,
    remove_tokens: int,
    keep_tokens: int,
    uncertain_tokens: int,
) -> AuditTrace:
    base = make_counterfactual_trace()
    segments = [
        replace(
            base.segments[0],
            segment_id="remove",
            token_count=remove_tokens,
            content_hash=f"{task_id}-{framework}-remove",
        ),
        replace(
            base.segments[0],
            segment_id="keep",
            ordinal=1,
            token_count=keep_tokens,
            content_hash=f"{task_id}-{framework}-keep",
        ),
    ]
    annotations = [
        ReferenceAnnotation(
            segment_id="remove",
            annotator_id="consensus",
            decision="remove",
            adjudicated=True,
        ),
        ReferenceAnnotation(
            segment_id="keep",
            annotator_id="consensus",
            decision="keep",
            adjudicated=True,
        ),
    ]
    if uncertain_tokens:
        segments.append(
            replace(
                base.segments[0],
                segment_id="uncertain",
                ordinal=2,
                token_count=uncertain_tokens,
                content_hash=f"{task_id}-{framework}-uncertain",
            )
        )
        annotations.append(
            ReferenceAnnotation(
                segment_id="uncertain",
                annotator_id="consensus",
                decision="uncertain",
                adjudicated=True,
            )
        )
    return replace(
        base,
        schema_version="1.2.1",
        trace_id=f"{task_id}-{framework}",
        task_id=task_id,
        framework=framework,
        task_success=True,
        evidence_tier="natural",
        dataset_split="test",
        segments=tuple(segments),
        reference_annotations=tuple(annotations),
        detected_labels={"remove": ("heuristic",)},
    )


if __name__ == "__main__":
    unittest.main()
