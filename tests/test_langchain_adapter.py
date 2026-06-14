from __future__ import annotations

import unittest
from dataclasses import dataclass

from context_auditor.langchain_adapter import convert_langchain_message


@dataclass(frozen=True)
class FakeLangChainMessage:
    type: str
    content: str


class LangChainAdapterTests(unittest.TestCase):
    def test_converts_langchain_roles_to_trace_roles(self) -> None:
        cases = [
            (FakeLangChainMessage("human", "hello"), "user"),
            (FakeLangChainMessage("ai", "answer"), "assistant"),
            (FakeLangChainMessage("system", "rules"), "system"),
            (FakeLangChainMessage("tool", "tool result"), "tool"),
        ]
        for message, expected_role in cases:
            converted = convert_langchain_message(message)
            self.assertEqual(converted.role, expected_role)
            self.assertEqual(converted.content, message.content)


if __name__ == "__main__":
    unittest.main()
