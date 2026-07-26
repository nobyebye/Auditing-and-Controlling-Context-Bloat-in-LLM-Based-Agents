import os
import unittest

from context_auditor.adapters.frameworks import (
    LangChainCaptureCallback,
    LangChainContextAdapter,
    langchain_available,
)
from context_auditor.adapters.providers import DeepSeekProvider, MockProvider
from context_auditor.adapters.providers.deepseek import estimate_cost_usd
from context_auditor.domain.models import Message, ProviderUsage


class ProviderTests(unittest.TestCase):
    def test_mock_returns_usage(self):
        response = MockProvider().invoke((Message("user", "hello world"),))
        self.assertGreater(response.usage.total_tokens or 0, 0)

    def test_mock_uses_last_user_message(self):
        response = MockProvider().invoke(
            (Message("user", "first"), Message("user", "second"))
        )
        self.assertIn("second", response.content)

    def test_deepseek_key_is_hidden_from_repr(self):
        provider = DeepSeekProvider(model="test", api_key="private")
        self.assertNotIn("private", repr(provider))

    def test_deepseek_environment_factory(self):
        original = os.environ.get("DEEPSEEK_API_KEY")
        os.environ["DEEPSEEK_API_KEY"] = "test-key"
        try:
            provider = DeepSeekProvider.from_environment("deepseek-v4-flash")
            self.assertEqual(provider.model, "deepseek-v4-flash")
        finally:
            if original is None:
                os.environ.pop("DEEPSEEK_API_KEY", None)
            else:
                os.environ["DEEPSEEK_API_KEY"] = original

    def test_deepseek_cost_uses_model_pricing(self):
        cost = estimate_cost_usd(
            "deepseek-v4-flash",
            ProviderUsage(input_tokens=1000, output_tokens=100, cached_input_tokens=200),
        )
        self.assertIsNotNone(cost)
        self.assertGreater(cost or 0, 0)


@unittest.skipUnless(langchain_available(), "langchain-core not installed")
class LangChainIntegrationTests(unittest.TestCase):
    def test_converts_real_langchain_messages(self):
        from langchain_core.messages import HumanMessage, SystemMessage

        converted = LangChainContextAdapter().convert(
            [SystemMessage(content="system"), HumanMessage(content="hello")]
        )
        self.assertEqual([item.role for item in converted], ["system", "user"])

    def test_rejects_unknown_objects(self):
        with self.assertRaises(TypeError):
            LangChainContextAdapter().convert([object()])

    def test_callback_captures_real_message_batch(self):
        from langchain_core.messages import HumanMessage

        class CaptureSpy:
            def __init__(self):
                self.requests = []

            def execute(self, request):
                self.requests.append(request)
                return request

        spy = CaptureSpy()
        callback = LangChainCaptureCallback(
            spy,
            lambda messages: type("Request", (), {"messages": messages})(),
        )
        callback.on_chat_model_start({}, [[HumanMessage(content="hello")]])
        self.assertEqual(spy.requests[0].messages[0].role, "user")


if __name__ == "__main__":
    unittest.main()
