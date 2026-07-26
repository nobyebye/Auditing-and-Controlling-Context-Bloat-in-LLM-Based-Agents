import tempfile
import unittest
from pathlib import Path

from context_auditor.adapters.common import DefaultIdGenerator, RegexTokenizer, UtcClock
from context_auditor.adapters.storage import JsonlTraceRepository
from context_auditor.application.capture import CaptureContext
from context_auditor.application.segmentation import label_source, segment_messages
from context_auditor.domain.enums import PrivacyMode, SourceType
from context_auditor.domain.models import CaptureRequest, Message


class CaptureTests(unittest.TestCase):
    def test_explicit_source_has_priority(self):
        message = Message("system", "anything", metadata={"source_type": "memory"})
        self.assertEqual(label_source(message), SourceType.MEMORY)

    def test_tool_role_is_tool_source(self):
        self.assertEqual(label_source(Message("tool", "result")), SourceType.TOOL)

    def test_user_role_is_user_source(self):
        self.assertEqual(label_source(Message("user", "question")), SourceType.USER)

    def test_retrieval_is_split_by_line(self):
        segments = segment_messages(
            (Message("system", "Retrieved context:\nDoc A\nDoc B"),),
            RegexTokenizer(),
            PrivacyMode.FULL,
        )
        self.assertEqual(len(segments), 2)

    def test_segments_have_parent_ids(self):
        segments = segment_messages(
            (Message("user", "hello"),), RegexTokenizer(), PrivacyMode.FULL
        )
        self.assertEqual(segments[0].parent_message_id, "m0000")

    def test_capture_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "trace.jsonl"
            repository = JsonlTraceRepository(path)
            trace = CaptureContext(
                repository, RegexTokenizer(), UtcClock(), DefaultIdGenerator()
            ).execute(make_request((Message("user", "hello"),)))
            self.assertTrue(path.is_file())
            self.assertEqual(trace.metrics["total_tokens"], 1)

    def test_capture_redacts_stored_messages(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = JsonlTraceRepository(Path(temporary) / "trace.jsonl")
            trace = CaptureContext(
                repository, RegexTokenizer(), UtcClock(), DefaultIdGenerator()
            ).execute(make_request((Message("user", "user@example.com"),)))
            self.assertNotIn("user@example.com", trace.messages[0].content)

    def test_capture_flags_duplicates(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = JsonlTraceRepository(Path(temporary) / "trace.jsonl")
            messages = (
                Message("tool", "same"),
                Message("tool", "same"),
            )
            trace = CaptureContext(
                repository, RegexTokenizer(), UtcClock(), DefaultIdGenerator()
            ).execute(make_request(messages))
            self.assertIn("duplicate_segments", trace.risk_flags)


def make_request(messages: tuple[Message, ...]) -> CaptureRequest:
    return CaptureRequest(
        experiment_id="test",
        run_id="20260726T120000Z__custom-react__mock__v1__05bd18f",
        task_id="task",
        framework="custom-react",
        provider="mock",
        model="mock",
        configuration="baseline",
        workflow_family="test",
        dataset_name="controlled",
        dataset_version="v1",
        repetition_id=0,
        seed=42,
        invocation_index=0,
        messages=messages,
        config_hash="abc",
    )


if __name__ == "__main__":
    unittest.main()
