from __future__ import annotations

import unittest

from unittest.mock import patch

from context_auditor.cli import build_parser
from context_auditor import (
    DeepSeekChatProvider,
    Message,
    MockChatProvider,
    provider_environment_status,
    provider_from_environment,
)


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

    def test_provider_factory_returns_deepseek_without_exposing_key(self) -> None:
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "secret-test-key"}, clear=True):
            provider = provider_from_environment("deepseek", "deepseek-v4-flash")
        self.assertIsInstance(provider, DeepSeekChatProvider)
        self.assertEqual(provider.provider_name, "deepseek")
        self.assertEqual(provider.model, "deepseek-v4-flash")
        self.assertEqual(provider.base_url, "https://api.deepseek.com")
        self.assertNotIn("secret-test-key", repr(provider))

    def test_provider_environment_status_never_returns_secret_values(self) -> None:
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "secret-test-key"}, clear=True):
            status = provider_environment_status("deepseek")
        self.assertEqual(status["provider"], "deepseek")
        self.assertEqual(status["required_environment"]["DEEPSEEK_API_KEY"], "SET")
        self.assertNotIn("secret-test-key", str(status))

    def test_cli_exposes_check_provider_command(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["check-provider", "--provider", "deepseek", "--model", "deepseek-v4-flash"])
        self.assertEqual(args.provider, "deepseek")
        self.assertEqual(args.model, "deepseek-v4-flash")
        self.assertTrue(callable(args.func))


if __name__ == "__main__":
    unittest.main()
