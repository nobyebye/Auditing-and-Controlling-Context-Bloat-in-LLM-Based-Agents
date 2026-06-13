from __future__ import annotations

import unittest

from context_auditor import Message, RuntimeAuditor, TraceMetadata
from context_auditor.mitigation import filter_irrelevant_segments, remove_near_duplicate_segments
from context_auditor.mitigation_eval import evaluate_mitigation_strategies, final_invocations, summarize_mitigation_rows
from experiments.retrieval import retrieve_documents


def metadata(task_id: str = "task") -> TraceMetadata:
    return TraceMetadata(
        task_id=task_id,
        framework="custom-react",
        provider="mock",
        model="mock-llm",
        configuration="retrieval_irrelevant",
        workflow_family="retrieval_qa",
    )


class RetrievalAndMitigationEvalTests(unittest.TestCase):
    def test_local_retrieval_ranks_relevant_document(self) -> None:
        docs = retrieve_documents("Which policy covers remote work eligibility?", top_k=1)
        self.assertEqual(docs[0].doc_id, "policy-remote")

    def test_near_duplicate_metrics_and_removal(self) -> None:
        auditor = RuntimeAuditor()
        trace = auditor.capture(
            metadata(),
            [
                Message("system", "Retrieved context:\nRemote work eligibility needs manager approval."),
                Message("system", "Retrieved context:\nRemote work eligibility needs manager approval now."),
                Message("user", "remote work eligibility"),
            ],
        )
        self.assertGreaterEqual(trace.metrics["near_duplicate_segment_count"], 1)
        _, report = remove_near_duplicate_segments(trace, threshold=0.5)
        self.assertEqual(report.removed_segments, 1)

    def test_irrelevant_filter_removes_unrelated_retrieval(self) -> None:
        auditor = RuntimeAuditor()
        trace = auditor.capture(
            metadata(),
            [
                Message("system", "Retrieved context:\nHardware replacement requests are handled by support."),
                Message("user", "remote work eligibility"),
            ],
        )
        _, report = filter_irrelevant_segments(trace, "remote work eligibility")
        self.assertEqual(report.removed_segments, 1)

    def test_mitigation_eval_uses_final_invocations(self) -> None:
        auditor = RuntimeAuditor()
        first = auditor.capture(metadata("task-a"), [Message("user", "remote")])
        second = auditor.capture(
            metadata("task-a"),
            [
                Message("system", "Retrieved context:\nRemote work eligibility needs manager approval."),
                Message("system", "Retrieved context:\nRemote work eligibility needs manager approval."),
                Message("user", "remote"),
            ],
            task_success=True,
            task_output="remote answer",
        )
        finals = final_invocations([first, second])
        self.assertEqual(finals, [second])
        rows = evaluate_mitigation_strategies([first, second])
        summary = summarize_mitigation_rows(rows)
        self.assertIn("exact_duplicate_removal", summary)
        self.assertEqual(summary["exact_duplicate_removal"]["task_success_rate"], 1.0)
        self.assertEqual(summary["exact_duplicate_removal"]["success_preservation_proxy_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
