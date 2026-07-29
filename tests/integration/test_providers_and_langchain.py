import hashlib
import json
import os
import unittest
from unittest.mock import patch

from context_auditor.adapters.frameworks import (
    LangChainCaptureCallback,
    LangChainContextAdapter,
    LangChainRuntime,
    langchain_available,
)
from context_auditor.adapters.providers import DeepSeekProvider, MockProvider
from context_auditor.adapters.providers.deepseek import estimate_cost_usd
from context_auditor.adapters.providers.payload import build_openai_payload
from context_auditor.domain.models import (
    Message,
    ModelRequestEnvelope,
    ProviderUsage,
    ToolCall,
    ToolDefinition,
)
from context_auditor.experiments.external_workflow import build_tool_follow_up_request


class ProviderTests(unittest.TestCase):
    def test_mock_returns_usage(self):
        response = MockProvider().invoke(
            ModelRequestEnvelope((Message("user", "hello world"),))
        )
        self.assertGreater(response.usage.total_tokens or 0, 0)

    def test_mock_uses_last_user_message(self):
        response = MockProvider().invoke(
            ModelRequestEnvelope(
                (Message("user", "first"), Message("user", "second"))
            )
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

    def test_deepseek_record_hash_matches_transmitted_body(self):
        captured = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(
                    {
                        "id": "response-1",
                        "choices": [{"message": {"content": "ok"}}],
                        "usage": {
                            "prompt_tokens": 1,
                            "completion_tokens": 1,
                            "total_tokens": 2,
                        },
                    }
                ).encode("utf-8")

        def fake_urlopen(api_request, timeout):
            captured["body"] = api_request.data
            return Response()

        provider = DeepSeekProvider(model="test", api_key="private")
        with patch(
            "context_auditor.adapters.providers.deepseek.request.urlopen",
            fake_urlopen,
        ):
            response = provider.invoke(
                ModelRequestEnvelope((Message("user", "hello"),))
            )
        self.assertEqual(
            response.request_record.payload_sha256,
            hashlib.sha256(captured["body"]).hexdigest(),
        )

    def test_tool_follow_up_serializes_required_provider_fields(self):
        task = {
            "task_id": "tool-1",
            "workflow_family": "multi_step_tool",
            "tool_results": {"calculator": {"value": 4}},
        }
        initial = ModelRequestEnvelope(
            messages=(Message("user", "calculate"),),
            tools=(
                ToolDefinition(
                    name="calculator",
                    description="Calculate.",
                    parameters={"type": "object"},
                ),
            ),
        )
        follow_up = build_tool_follow_up_request(
            initial,
            task=task,
            framework="custom-react",
            tool_calls=(
                ToolCall(
                    call_id="call-1",
                    name="calculator",
                    arguments={"expression": "2+2"},
                ),
            ),
            assistant_content="I will calculate that.",
        )
        payload = build_openai_payload(follow_up, "deepseek-v4-flash")
        assistant = payload["messages"][1]
        tool = payload["messages"][2]
        self.assertEqual(assistant["tool_calls"][0]["id"], "call-1")
        self.assertEqual(
            assistant["tool_calls"][0]["function"]["arguments"],
            '{"expression":"2+2"}',
        )
        self.assertEqual(tool["tool_call_id"], "call-1")

    def test_tool_message_without_call_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "tool_call_id"):
            build_openai_payload(
                ModelRequestEnvelope((Message("tool", "result"),)),
                "deepseek-v4-flash",
            )


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

    def test_tool_messages_round_trip_required_provider_fields(self):
        from langchain_core.messages import AIMessage, ToolMessage

        converted = LangChainContextAdapter().convert(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "call-1",
                            "name": "calculator",
                            "args": {"expression": "2+2"},
                            "type": "tool_call",
                        }
                    ],
                ),
                ToolMessage(content="4", tool_call_id="call-1"),
            ]
        )
        payload = build_openai_payload(
            ModelRequestEnvelope(converted),
            "deepseek-v4-flash",
        )
        self.assertEqual(payload["messages"][0]["tool_calls"][0]["id"], "call-1")
        self.assertEqual(payload["messages"][1]["tool_call_id"], "call-1")

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

    def test_runtime_preserves_bound_tool_schema_at_provider_boundary(self):
        response, captured = LangChainRuntime(MockProvider()).invoke(
            ModelRequestEnvelope(
                messages=(Message("user", "calculate"),),
                tools=(
                    ToolDefinition(
                        name="calculator",
                        description="Calculate an expression.",
                        parameters={
                            "type": "object",
                            "properties": {
                                "expression": {"type": "string"},
                            },
                        },
                    ),
                ),
            )
        )
        self.assertEqual(captured[0].role, "user")
        self.assertEqual(response.tool_calls[0].name, "calculator")
        payload = response.request_record.redacted_payload
        self.assertEqual(payload["tools"][0]["function"]["name"], "calculator")


if __name__ == "__main__":
    unittest.main()
