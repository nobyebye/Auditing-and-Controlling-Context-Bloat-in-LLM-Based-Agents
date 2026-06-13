from __future__ import annotations

import unittest

from context_auditor import Message, RuntimeAuditor, TraceMetadata
from context_auditor.bloat import classify_bloat, summarize_traces
from context_auditor.evaluation import keyword_success
from context_auditor.mitigation import remove_exact_duplicate_segments


def make_metadata(task_id: str = "task") -> TraceMetadata:
    return TraceMetadata(
        task_id=task_id,
        framework="custom-react",
        provider="mock",
        model="mock-llm",
        configuration="retrieval",
        workflow_family="retrieval_qa",
    )


class BloatAndMitigationTests(unittest.TestCase):
    def test_classifies_duplicate_retrieval_bloat(self) -> None:
        auditor = RuntimeAuditor()
        trace = auditor.capture(
            make_metadata(),
            [
                Message("system", "Retrieved context:\nRepeated policy text"),
                Message("system", "Retrieved context:\nRepeated policy text"),
                Message("user", "Question"),
            ],
        )

        labels = classify_bloat(trace)
        self.assertIn("high_redundancy", labels)
        self.assertIn("redundant_source:retrieval", labels)

    def test_duplicate_removal_report(self) -> None:
        auditor = RuntimeAuditor()
        trace = auditor.capture(
            make_metadata(),
            [
                Message("system", "Retrieved context:\nRepeated policy text"),
                Message("system", "Retrieved context:\nRepeated policy text"),
                Message("user", "Question"),
            ],
        )

        kept, report = remove_exact_duplicate_segments(trace)
        self.assertEqual(len(kept), 2)
        self.assertEqual(report.removed_segments, 1)
        self.assertGreater(report.removed_tokens, 0)
        self.assertGreater(report.token_reduction_ratio, 0)

    def test_summarize_traces_groups_by_configuration(self) -> None:
        auditor = RuntimeAuditor()
        first = auditor.capture(make_metadata("task-a"), [Message("user", "short")])
        second = auditor.capture(
            make_metadata("task-a"),
            [Message("user", "short " * 20)],
            task_success=True,
            task_output="answer",
        )

        summary = summarize_traces([first, second])
        self.assertEqual(summary["trace_count"], 2)
        self.assertIn("retrieval", summary["by_configuration"])
        self.assertGreater(summary["mean_context_growth_rate"], 0)
        self.assertEqual(summary["by_configuration"]["retrieval"]["task_success_rate"], 1.0)

    def test_mitigated_configuration_pairs(self) -> None:
        auditor = RuntimeAuditor()
        original = auditor.capture(
            make_metadata("task-b"),
            [
                Message("system", "Retrieved context:\nSame doc"),
                Message("system", "Retrieved context:\nSame doc"),
                Message("user", "Question"),
            ],
            task_success=True,
            task_output="answer",
        )
        mitigated_metadata = TraceMetadata(
            task_id="task-b-mitigated",
            framework="custom-react",
            provider="mock",
            model="mock-llm",
            configuration="retrieval_mitigated",
            workflow_family="retrieval_qa",
        )
        mitigated = auditor.capture(
            mitigated_metadata,
            [
                Message("system", "Retrieved context:\nSame doc"),
                Message("user", "Question"),
            ],
            task_success=True,
            task_output="answer",
        )

        summary = summarize_traces([original, mitigated])
        self.assertIn("retrieval -> retrieval_mitigated", summary["mitigation_pairs"])

    def test_keyword_success(self) -> None:
        self.assertTrue(keyword_success("Final answer contains Runtime Context Auditor", "context"))
        self.assertFalse(keyword_success("No relevant answer", "context"))


if __name__ == "__main__":
    unittest.main()
