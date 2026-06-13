from __future__ import annotations

import unittest

from context_auditor import Message
from context_auditor.message_mitigation import apply_message_mitigation


class MessageMitigationTests(unittest.TestCase):
    def test_duplicate_message_removal(self) -> None:
        messages = [
            Message("system", "Retrieved context:\nRemote work policy."),
            Message("system", "Retrieved context:\nRemote work policy."),
            Message("user", "remote work"),
        ]
        mitigated = apply_message_mitigation(messages, "exact_duplicate_removal", "remote work")
        self.assertEqual(len(mitigated), 2)

    def test_irrelevant_context_filter_keeps_relevant_lines(self) -> None:
        messages = [
            Message(
                "system",
                "Retrieved context:\nRemote work requires approval.\nHardware requests go to support.",
            ),
            Message("user", "remote work approval"),
        ]
        mitigated = apply_message_mitigation(messages, "irrelevant_context_filter", "remote work approval")
        self.assertIn("Remote work requires approval.", mitigated[0].content)
        self.assertNotIn("Hardware requests", mitigated[0].content)


if __name__ == "__main__":
    unittest.main()
