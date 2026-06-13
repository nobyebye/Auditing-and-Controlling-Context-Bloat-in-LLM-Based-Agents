from __future__ import annotations

import unittest

from context_auditor import Message, RuntimeAuditor, TraceMetadata
from context_auditor.provenance import SourceType, label_message_source, segment_messages


class ProvenanceTests(unittest.TestCase):
    def test_labels_core_sources(self) -> None:
        cases = [
            (Message("system", "You are helpful."), SourceType.SYSTEM),
            (Message("user", "Question"), SourceType.USER),
            (Message("system", "Retrieved context:\nDoc"), SourceType.RETRIEVAL),
            (Message("system", "Conversation history:\nEarlier turn"), SourceType.MEMORY),
            (Message("tool", "calculator result: 42"), SourceType.TOOL),
            (Message("assistant", "Thought: use a tool"), SourceType.GENERATED_TRACE),
        ]
        for message, expected in cases:
            self.assertEqual(label_message_source(message), expected)

    def test_segments_include_hashes_and_counts(self) -> None:
        segments = segment_messages([Message("user", "Hello world")])
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].token_count, 2)
        self.assertEqual(segments[0].char_count, 11)
        self.assertTrue(segments[0].content_hash)
        self.assertTrue(segments[0].normalized_hash)


class RuntimeAuditorTests(unittest.TestCase):
    def test_capture_builds_trace_schema(self) -> None:
        auditor = RuntimeAuditor()
        metadata = TraceMetadata(
            task_id="task-1",
            framework="custom-react",
            provider="mock",
            model="mock-llm",
            configuration="baseline",
            workflow_family="retrieval_qa",
        )
        trace = auditor.capture(
            metadata,
            [
                Message("system", "Retrieved context:\nSame doc"),
                Message("system", "Retrieved context:\nSame doc"),
                Message("user", "Question"),
            ],
        )
        self.assertEqual(trace.invocation_index, 0)
        self.assertEqual(trace.schema_version, "0.5.0")
        self.assertEqual(trace.experiment_id, "pilot")
        self.assertEqual(trace.dataset_name, "controlled_synthetic")
        self.assertTrue(trace.config_hash)
        self.assertEqual(trace.metrics["duplicate_segment_count"], 1)
        self.assertGreater(trace.metrics["redundancy_ratio"], 0)
        self.assertLess(trace.metrics["unique_information_ratio"], 1)
        self.assertIn("duplicate_retrieval", trace.risk_flags)

    def test_growth_guard_flags_later_invocation(self) -> None:
        auditor = RuntimeAuditor()
        metadata = TraceMetadata("task-2", "custom-react", "mock", "mock-llm", "tool", "multi_step_tool")
        auditor.capture(metadata, [Message("user", "short")])
        trace = auditor.capture(metadata, [Message("user", "word " * 120)])
        self.assertIn("growth_spike", trace.risk_flags)


if __name__ == "__main__":
    unittest.main()
