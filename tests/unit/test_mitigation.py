import unittest

from context_auditor.adapters.common import RegexTokenizer
from context_auditor.application.mitigation import ApplyMitigation
from context_auditor.domain.models import Message


class MitigationTests(unittest.TestCase):
    def setUp(self):
        self.use_case = ApplyMitigation(RegexTokenizer())

    def test_none_keeps_all_messages(self):
        messages = (Message("user", "hello"),)
        self.assertEqual(self.use_case.execute(messages, "hello", "none").messages, messages)

    def test_exact_removes_duplicate_tool_output(self):
        messages = (Message("tool", "result"), Message("tool", "result"))
        result = self.use_case.execute(messages, "query", "exact")
        self.assertEqual(len(result.messages), 1)
        self.assertEqual(result.decisions[0].reason, "exact_duplicate")

    def test_exact_does_not_remove_duplicate_user_messages(self):
        messages = (Message("user", "same"), Message("user", "same"))
        self.assertEqual(len(self.use_case.execute(messages, "same", "exact").messages), 2)

    def test_source_aware_removes_irrelevant_retrieval(self):
        messages = (
            Message("system", "hardware replacement", metadata={"source_type": "retrieval"}),
            Message("user", "remote policy"),
        )
        result = self.use_case.execute(messages, "remote policy", "source-aware")
        self.assertEqual(len(result.messages), 1)
        self.assertEqual(result.decisions[0].reason, "low_query_relevance")

    def test_unknown_strategy_fails(self):
        with self.assertRaises(ValueError):
            self.use_case.execute((), "query", "unknown")

    def test_last_n_preserves_user(self):
        messages = tuple(Message("tool", f"{index}") for index in range(10)) + (
            Message("user", "question"),
        )
        result = self.use_case.execute(messages, "question", "last-n")
        self.assertIn("question", [item.content for item in result.messages])


if __name__ == "__main__":
    unittest.main()
