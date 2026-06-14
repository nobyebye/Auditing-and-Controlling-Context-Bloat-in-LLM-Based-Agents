"""LangChain-compatible pilot runner.

The runner prefers real ``langchain_core.messages`` classes when they are
installed, and falls back to a small local message shape with the same ``type``
and ``content`` attributes. This keeps CI deterministic while exercising the
same callback boundary used by LangChain chat models.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from context_auditor import Message, RuntimeAuditor, TraceMetadata
from context_auditor.evaluation import keyword_success
from context_auditor.langchain_adapter import AuditingLangChainCallback, convert_langchain_message
from context_auditor.message_mitigation import apply_message_mitigation

from .config import load_experiment_config
from .custom_react import AgentConfig, safe_calculate
from .datasets import load_controlled_dataset
from .retrieval import Document, render_retrieved_context, retrieve_documents
from .tasks import Task


@dataclass(frozen=True)
class LocalLangChainMessage:
    type: str
    content: str


class LangChainCompatibleAgent:
    def __init__(
        self,
        auditor: RuntimeAuditor,
        provider: str = "mock",
        model: str = "mock-llm",
        experiment_id: str = "pilot",
        run_id: str = "run-001",
        dataset_name: str = "controlled_synthetic",
        policy_docs: list[Document] | None = None,
        memory_items: list[str] | None = None,
    ) -> None:
        self.auditor = auditor
        self.provider = provider
        self.model = model
        self.experiment_id = experiment_id
        self.run_id = run_id
        self.dataset_name = dataset_name
        self.policy_docs = policy_docs or []
        self.memory_items = memory_items or []

    def run(self, task: Task, config: AgentConfig) -> str:
        metadata = TraceMetadata(
            task_id=f"{task.task_id}:{config.configuration}",
            framework="langchain",
            provider=self.provider,
            model=self.model,
            configuration=config.configuration,
            workflow_family=task.workflow_family,
            experiment_id=self.experiment_id,
            run_id=self.run_id,
            dataset_name=self.dataset_name,
            config=asdict(config),
            task_expected_keyword=task.expected_keyword,
        )
        messages = self._base_messages(task, config)
        messages = self._mitigate_messages(messages, task, config)
        self._capture_callback(metadata, messages)

        if config.use_tools:
            first_result = safe_calculate(self._first_expression(task.prompt))
            messages.append(Message(role="assistant", content="Thought: I should use the calculator.\nAction: calculator"))
            messages.append(Message(role="tool", content=f"calculator result: {first_result:g}"))
            if config.repeat_tool_output:
                messages.append(Message(role="tool", content=f"calculator result: {first_result:g}"))
            messages = self._mitigate_messages(messages, task, config)
            self._capture_callback(metadata, messages)

            second_result = self._finish_tool_task(task.prompt, first_result)
            answer = f"{second_result:g}"
            messages.append(Message(role="assistant", content=f"Final answer: {answer}"))
            self.auditor.capture(
                metadata,
                self._roundtrip_langchain_messages(messages),
                task_success=keyword_success(answer, task.expected_keyword),
                task_output=answer,
            )
            return answer

        answer = self._answer_without_tools(task, config, messages)
        messages.append(Message(role="assistant", content=f"Final answer: {answer}"))
        self.auditor.capture(
            metadata,
            self._roundtrip_langchain_messages(messages),
            task_success=keyword_success(answer, task.expected_keyword),
            task_output=answer,
        )
        return answer

    def _capture_callback(self, metadata: TraceMetadata, messages: list[Message]) -> None:
        callback = AuditingLangChainCallback(self.auditor, metadata)
        callback.on_chat_model_start({}, [self._to_langchain_messages(messages)])

    def _to_langchain_messages(self, messages: list[Message]) -> list[Any]:
        return [_make_langchain_message(message.role, message.content) for message in messages]

    def _roundtrip_langchain_messages(self, messages: list[Message]) -> list[Message]:
        return [convert_langchain_message(message) for message in self._to_langchain_messages(messages)]

    def _mitigate_messages(self, messages: list[Message], task: Task, config: AgentConfig) -> list[Message]:
        return apply_message_mitigation(
            messages,
            strategy=config.mitigation_strategy,
            query=task.prompt,
            min_overlap_ratio=config.irrelevance_min_overlap,
        )

    def _base_messages(self, task: Task, config: AgentConfig) -> list[Message]:
        messages = [
            Message(role="system", content="You are a LangChain research agent for context bloat auditing."),
            Message(role="system", content="Available tools: calculator. Agent scratchpad is appended after tool use."),
        ]
        if config.retrieval_top_k:
            retrieved_documents = retrieve_documents(
                task.prompt,
                top_k=config.retrieval_top_k,
                corpus=self.policy_docs,
                include_irrelevant=config.include_irrelevant_retrieval,
            )
            retrieved = render_retrieved_context(retrieved_documents)
            messages.append(Message(role="system", content=f"Retrieved context:\n{retrieved}"))
            if config.duplicate_retrieval:
                messages.append(Message(role="system", content=f"Retrieved context:\n{retrieved}"))
        if config.include_memory:
            memory = "Conversation history:\n" + "\n".join(self.memory_items)
            messages.append(Message(role="system", content=memory))
            if config.duplicate_memory:
                messages.append(Message(role="system", content=memory))
        messages.append(Message(role="user", content=task.prompt))
        return messages

    def _answer_without_tools(self, task: Task, config: AgentConfig, messages: list[Message]) -> str:
        if config.retrieval_top_k:
            retrieved_lines = [
                line
                for message in messages
                if "Retrieved context:" in message.content
                for line in message.content.splitlines()[1:]
                if line.strip()
            ]
            return next(
                (line for line in retrieved_lines if task.expected_keyword in line.lower()),
                retrieved_lines[0] if retrieved_lines else "Insufficient relevant retrieved context.",
            )
        if config.include_memory:
            memory_lines = [
                line
                for message in messages
                if "Conversation history:" in message.content
                for line in message.content.splitlines()[1:]
                if line.strip()
            ]
            return next(
                (line for line in memory_lines if task.expected_keyword in line.lower()),
                memory_lines[0] if memory_lines else "Insufficient relevant memory.",
            )
        return "Insufficient context in baseline configuration."

    def _first_expression(self, prompt: str) -> str:
        if "18 * 7" in prompt:
            return "18 * 7"
        if "125 / 5" in prompt:
            return "125 / 5"
        if "14 * 14" in prompt:
            return "14 * 14"
        return "1 + 1"

    def _finish_tool_task(self, prompt: str, first_result: float) -> float:
        if "add 42" in prompt:
            return first_result + 42
        if "subtract 9" in prompt:
            return first_result - 9
        if "add 4" in prompt:
            return first_result + 4
        return first_result


def run_langchain_pilot(
    output_path: str | Path | None = None,
    config_path: str | Path = "configs/langchain_pilot.json",
) -> None:
    experiment = load_experiment_config(config_path)
    dataset = load_controlled_dataset(experiment.dataset_name)
    output_path = output_path or experiment.output_path
    output = Path(output_path)
    if output.exists():
        output.unlink()
    auditor = RuntimeAuditor(output)
    agent = LangChainCompatibleAgent(
        auditor,
        provider=experiment.provider,
        model=experiment.model,
        experiment_id=experiment.experiment_id,
        run_id=experiment.run_id,
        dataset_name=experiment.dataset_name,
        policy_docs=dataset.policy_docs,
        memory_items=dataset.memory_items,
    )

    for workflow_family, configs in experiment.workflow_configs.items():
        for task in dataset.tasks_by_workflow(workflow_family):
            for config in configs:
                agent.run(task, config)


def _make_langchain_message(role: str, content: str) -> Any:
    try:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
    except ImportError:
        return LocalLangChainMessage(_langchain_type(role), content)

    if role == "system":
        return SystemMessage(content=content)
    if role in {"user", "human"}:
        return HumanMessage(content=content)
    if role == "tool":
        return ToolMessage(content=content, tool_call_id="controlled-tool")
    return AIMessage(content=content)


def _langchain_type(role: str) -> str:
    if role == "user":
        return "human"
    if role == "assistant":
        return "ai"
    return role
