"""Controlled retrieval, memory, and tool workflows."""

from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass

from context_auditor.application import ApplyMitigation
from context_auditor.domain.models import Message, MitigationDecision

from .config import WorkflowCondition

OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
NUMBER_EXPR_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([*/+-])\s*(\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class WorkflowState:
    messages: tuple[Message, ...]
    answer: str
    success: bool
    snapshots: tuple[tuple[Message, ...], ...]
    mitigation_decisions: tuple[MitigationDecision, ...]


def execute_workflow(
    task: dict,
    condition: WorkflowCondition,
    documents: list[dict],
    memory: list[str],
    mitigation: ApplyMitigation,
) -> WorkflowState:
    messages: list[Message] = [
        Message("system", "You are a controlled research agent for context auditing."),
        Message(
            "system",
            "Available tools: calculator. Agent scratchpad follows tool calls.",
            metadata={"source_type": "framework"},
        ),
    ]
    if condition.retrieval_top_k:
        selected = retrieve(task["prompt"], documents, condition.retrieval_top_k)
        if condition.include_irrelevant_retrieval and documents:
            irrelevant = next((doc for doc in reversed(documents) if doc not in selected), documents[-1])
            selected = [*selected, irrelevant]
        for document in selected:
            item = Message(
                "system",
                f"{document['title']}: {document['text']}",
                metadata={"source_type": "retrieval", "source_id": document["doc_id"]},
            )
            messages.append(item)
        if condition.duplicate_retrieval:
            messages.extend(
                [item for item in messages if item.metadata.get("source_type") == "retrieval"]
            )
    if condition.include_memory:
        memory_messages = [
            Message("system", item, metadata={"source_type": "memory"}) for item in memory
        ]
        messages.extend(memory_messages)
        if condition.duplicate_memory:
            messages.extend(memory_messages)
    messages.append(Message("user", task["prompt"]))

    decisions: tuple[MitigationDecision, ...] = ()
    if condition.mitigation_strategy != "none":
        result = mitigation.execute(
            tuple(messages), task["prompt"], normalize_strategy(condition.mitigation_strategy)
        )
        messages = list(result.messages)
        decisions = result.decisions
    snapshots: list[tuple[Message, ...]] = [tuple(messages)]

    if condition.use_tools:
        first_expression, final_expression = tool_expressions(task["prompt"])
        first = safe_calculate(first_expression)
        messages.append(
            Message(
                "assistant",
                "Thought: use calculator.\nAction: calculator",
                metadata={"source_type": "generated_trace"},
            )
        )
        tool_message = Message(
            "tool",
            f"calculator result: {first:g}",
            metadata={"source_type": "tool"},
        )
        messages.append(tool_message)
        if condition.repeat_tool_output:
            messages.append(tool_message)
        if condition.mitigation_strategy != "none":
            result = mitigation.execute(
                tuple(messages), task["prompt"], normalize_strategy(condition.mitigation_strategy)
            )
            messages = list(result.messages)
            decisions = (*decisions, *result.decisions)
        snapshots.append(tuple(messages))
        answer = f"{safe_calculate(final_expression.replace('RESULT', str(first))):g}"
    else:
        answer = answer_from_context(task, messages)

    messages.append(
        Message(
            "assistant",
            f"Final answer: {answer}",
            metadata={"source_type": "generated_trace"},
        )
    )
    snapshots.append(tuple(messages))
    success = str(task["expected_answer"]).casefold() in answer.casefold()
    return WorkflowState(tuple(messages), answer, success, tuple(snapshots), decisions)


def retrieve(query: str, documents: list[dict], top_k: int) -> list[dict]:
    query_tokens = set(re.findall(r"\w+", query.casefold()))
    scored = sorted(
        documents,
        key=lambda item: len(
            query_tokens & set(re.findall(r"\w+", f"{item['title']} {item['text']}".casefold()))
        ),
        reverse=True,
    )
    return scored[:top_k]


def answer_from_context(task: dict, messages: list[Message]) -> str:
    expected = str(task["expected_answer"]).casefold()
    candidates = [
        item.content
        for item in messages
        if item.metadata.get("source_type") in {"retrieval", "memory"}
    ]
    return next(
        (item for item in candidates if expected in item.casefold()),
        candidates[0] if candidates else "Insufficient context in baseline configuration.",
    )


def tool_expressions(prompt: str) -> tuple[str, str]:
    matches = NUMBER_EXPR_RE.findall(prompt)
    if not matches:
        return "1 + 1", "RESULT"
    left, operator_symbol, right = matches[0]
    first = f"{left} {operator_symbol} {right}"
    lowered = prompt.casefold()
    trailing = re.search(r"(?:add|subtract)\s+(\d+(?:\.\d+)?)", lowered)
    if not trailing:
        return first, "RESULT"
    symbol = "+" if "add" in lowered[trailing.start() : trailing.end()] else "-"
    return first, f"RESULT {symbol} {trailing.group(1)}"


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


def normalize_strategy(strategy: str) -> str:
    return {
        "exact_duplicate_removal": "exact",
        "irrelevant_context_filter": "source-aware",
        "combined": "source-aware",
    }.get(strategy, strategy)
