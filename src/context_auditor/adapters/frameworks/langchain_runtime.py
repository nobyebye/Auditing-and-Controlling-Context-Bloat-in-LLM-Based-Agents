"""A provider-backed LangChain chat model used by the formal experiment."""

from __future__ import annotations

from typing import Any

from dataclasses import replace

from context_auditor.domain.models import (
    Message,
    ModelRequestEnvelope,
    ProviderResponse,
)
from context_auditor.ports import ChatProvider

from .langchain import LangChainContextAdapter, langchain_available


class LangChainRuntime:
    def __init__(self, provider: ChatProvider) -> None:
        if not langchain_available():
            raise RuntimeError("langchain-core is required for the LangChain runtime")
        self.provider = provider

    def invoke(
        self,
        request: ModelRequestEnvelope,
    ) -> tuple[ProviderResponse, tuple[Message, ...]]:
        from langchain_core.callbacks import BaseCallbackHandler
        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_core.messages import AIMessage
        from langchain_core.outputs import ChatGeneration, ChatResult
        from langchain_core.runnables import Runnable
        from pydantic import PrivateAttr

        provider = self.provider
        adapter = LangChainContextAdapter()

        class Recorder(BaseCallbackHandler):
            def __init__(self) -> None:
                self.messages: tuple[Message, ...] = ()

            def on_chat_model_start(
                self,
                serialized: dict[str, Any],
                batches: list[list[Any]],
                **kwargs: Any,
            ) -> None:
                self.messages = adapter.convert(batches[0])

        class ProviderChatModel(BaseChatModel):
            _last_response: ProviderResponse | None = PrivateAttr(default=None)

            @property
            def _llm_type(self) -> str:
                return "context-auditor-provider"

            @property
            def _identifying_params(self) -> dict[str, Any]:
                return {"provider": provider.provider_name, "model": provider.model}

            def _generate(
                self,
                lc_messages: list[Any],
                stop: list[str] | None = None,
                run_manager: Any = None,
                **kwargs: Any,
            ) -> ChatResult:
                converted = adapter.convert(lc_messages)
                self._last_response = provider.invoke(
                    replace(request, messages=converted)
                )
                message = AIMessage(
                    content=self._last_response.content,
                    response_metadata={
                        "latency_ms": self._last_response.latency_ms,
                        "response_id": self._last_response.response_id,
                    },
                )
                return ChatResult(generations=[ChatGeneration(message=message)])

            def bind_tools(
                self,
                tools: list[Any],
                *,
                tool_choice: str | None = None,
                **kwargs: Any,
            ) -> Runnable:
                bound = {"tools": tools, **kwargs}
                if tool_choice is not None:
                    bound["tool_choice"] = tool_choice
                return self.bind(**bound)

        from context_auditor.experiments.runner import to_langchain_messages

        recorder = Recorder()
        model = ProviderChatModel()
        invoker = (
            model.bind_tools([to_langchain_tool(tool) for tool in request.tools])
            if request.tools
            else model
        )
        invoker.invoke(
            to_langchain_messages(request.messages),
            config={"callbacks": [recorder]},
        )
        if model._last_response is None or not recorder.messages:
            raise RuntimeError("LangChain invocation completed without a captured request")
        return model._last_response, recorder.messages


def to_langchain_tool(tool) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": dict(tool.parameters),
        },
    }
