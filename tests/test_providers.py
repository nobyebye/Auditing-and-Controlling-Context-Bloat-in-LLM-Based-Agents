from __future__ import annotations

import unittest

from context_auditor import Message, MockChatProvider, provider_from_environment


class ProviderTests(unittest.TestCase):
    def test_mock_provider_echoes_last_user_message(self) -> None:
        provider = MockChatProvider(model="mock-test")
        answer = provider.complete([Message("user", "hello provider")])
        self.assertIn("hello provider", answer)
        self.assertEqual(provider.model, "mock-test")

    def test_provider_factory_returns_mock(self) -> None:
        provider = provider_from_environment("mock", "mock-factory")
        self.assertEqual(provider.provider_name, "mock")
        self.assertEqual(provider.model, "mock-factory")


if __name__ == "__main__":
    unittest.main()
