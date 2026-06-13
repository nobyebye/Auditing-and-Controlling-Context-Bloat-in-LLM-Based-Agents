from __future__ import annotations

import unittest

from context_auditor import Message, RuntimeAuditor, TraceMetadata
from context_auditor.bloat import classify_bloat, summarize_traces
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
        second = auditor.capture(make_metadata("task-a"), [Message("user", "short " * 20)])

        summary = summarize_traces([first, second])
        self.assertEqual(summary["trace_count"], 2)
        self.assertIn("retrieval", summary["by_configuration"])
        self.assertGreater(summary["mean_context_growth_rate"], 0)


if __name__ == "__main__":
    unittest.main()

