"""A small controlled ReAct-style agent used as the second implementation."""

from __future__ import annotations

import ast
import operator
from dataclasses import asdict, dataclass

from context_auditor import Message, RuntimeAuditor, TraceMetadata
from context_auditor.evaluation import keyword_success
from context_auditor.message_mitigation import apply_message_mitigation

from .retrieval import render_retrieved_context, retrieve_documents
from .tasks import MEMORY_ITEMS, Task


OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def safe_calculate(expression: str) -> float:
    def evaluate(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            return OPERATORS[type(node.op)](evaluate(node.left), evaluate(node.right))
        raise ValueError(f"Unsupported expression: {expression}")

    return evaluate(ast.parse(expression, mode="eval"))


@dataclass(frozen=True)
class AgentConfig:
    configuration: str
    retrieval_top_k: int = 0
    retrieval_strategy: str = "local_overlap"
    include_memory: bool = False
    use_tools: bool = False
    duplicate_retrieval: bool = False
    include_irrelevant_retrieval: bool = False
    duplicate_memory: bool = False
    repeat_tool_output: bool = False
    mitigation_strategy: str = "none"
    irrelevance_min_overlap: float = 0.05
    guard_mode: bool = False


class CustomReactAgent:
    def __init__(
        self,
        auditor: RuntimeAuditor,
        provider: str = "mock",
        model: str = "mock-llm",
        experiment_id: str = "pilot",
        run_id: str = "run-001",
        dataset_name: str = "controlled_synthetic",
    ) -> None:
        self.auditor = auditor
        self.provider = provider
        self.model = model
        self.experiment_id = experiment_id
        self.run_id = run_id
        self.dataset_name = dataset_name

    def run(self, task: Task, config: AgentConfig) -> str:
        metadata = TraceMetadata(
            task_id=f"{task.task_id}:{config.configuration}",
            framework="custom-react",
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
        self.auditor.capture(metadata, messages)

        if config.use_tools:
            first_result = safe_calculate(self._first_expression(task.prompt))
            messages.append(Message(role="assistant", content="Thought: I should use the calculator.\nAction: calculator"))
            messages.append(Message(role="tool", content=f"calculator result: {first_result:g}"))
            if config.repeat_tool_output:
                messages.append(Message(role="tool", content=f"calculator result: {first_result:g}"))
            messages = self._mitigate_messages(messages, task, config)
            self.auditor.capture(metadata, messages)

            second_result = self._finish_tool_task(task.prompt, first_result)
            answer = f"{second_result:g}"
            messages.append(Message(role="assistant", content=f"Final answer: {answer}"))
            self.auditor.capture(
                metadata,
                messages,
                task_success=keyword_success(answer, task.expected_keyword),
                task_output=answer,
            )
            return answer

        answer = self._answer_without_tools(task, config, messages)
        messages.append(Message(role="assistant", content=f"Final answer: {answer}"))
        self.auditor.capture(
            metadata,
            messages,
            task_success=keyword_success(answer, task.expected_keyword),
            task_output=answer,
        )
        return answer

    def _mitigate_messages(self, messages: list[Message], task: Task, config: AgentConfig) -> list[Message]:
        return apply_message_mitigation(
            messages,
            strategy=config.mitigation_strategy,
            query=task.prompt,
            min_overlap_ratio=config.irrelevance_min_overlap,
        )

    def _base_messages(self, task: Task, config: AgentConfig) -> list[Message]:
        messages = [
            Message(role="system", content="You are a controlled research agent for context auditing."),
            Message(role="system", content="Available tools: calculator. Agent scratchpad is appended after tool use."),
        ]
        if config.retrieval_top_k:
            retrieved_documents = retrieve_documents(
                task.prompt,
                top_k=config.retrieval_top_k,
                include_irrelevant=config.include_irrelevant_retrieval,
            )
            retrieved = render_retrieved_context(retrieved_documents)
            messages.append(Message(role="system", content=f"Retrieved context:\n{retrieved}"))
            if config.duplicate_retrieval:
                messages.append(Message(role="system", content=f"Retrieved context:\n{retrieved}"))
        if config.include_memory:
            memory = "Conversation history:\n" + "\n".join(MEMORY_ITEMS)
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
