"""Formal context construction and controlled agent execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from context_auditor.application import ApplyMitigation
from context_auditor.domain.models import Message, MitigationDecision, ProviderResponse

from .config import WorkflowCondition


@dataclass(frozen=True)
class InvocationResult:
    messages: tuple[Message, ...]
    response: ProviderResponse
    final: bool
    mitigation_decisions: tuple[MitigationDecision, ...] = ()
    attempt_index: int = 0


def execute_formal_workflow(
    task: dict,
    condition: WorkflowCondition,
    data: dict,
    framework: str,
    mitigation: ApplyMitigation,
    invoke: Callable[
        [tuple[Message, ...]],
        tuple[ProviderResponse, tuple[Message, ...], int],
    ],
) -> tuple[InvocationResult, ...]:
    messages = list(build_initial_context(task, condition, data, framework))
    decisions: tuple[MitigationDecision, ...] = ()
    if condition.mitigation_strategy != "none" and not condition.use_tools:
        result = mitigation.execute(
            tuple(messages),
            task["prompt"],
            normalize_strategy(condition.mitigation_strategy),
        )
        messages = list(result.messages)
        decisions = result.decisions

    if not condition.use_tools:
        response, captured, attempt = invoke(tuple(messages))
        return (InvocationResult(captured, response, True, decisions, attempt),)

    planning_prompt = Message(
        "system",
        "State which available tool should be used. Do not provide the final answer yet.",
        metadata={"source_type": "framework"},
    )
    messages.append(planning_prompt)
    planning_response, captured, attempt = invoke(tuple(messages))
    results = [InvocationResult(captured, planning_response, False, (), attempt)]
    messages.append(
        Message(
            "assistant",
            planning_response.content,
            metadata={"source_type": "generated_trace"},
        )
    )
    messages.append(build_tool_message(task, condition))
    if condition.repeat_tool_output:
        duplicate = build_tool_message(task, condition)
        messages.append(
            Message(
                duplicate.role,
                duplicate.content,
                metadata={
                    **duplicate.metadata,
                    "bloat_labels": merge_labels(
                        duplicate.metadata.get("bloat_labels", ()),
                        ("exact_duplicate",),
                    ),
                },
            )
        )
    messages.append(
        Message(
            "system",
            "Use the tool result above and provide only the final answer.",
            metadata={"source_type": "framework"},
        )
    )
    if condition.mitigation_strategy != "none":
        result = mitigation.execute(
            tuple(messages),
            task["prompt"],
            normalize_strategy(condition.mitigation_strategy),
        )
        messages = list(result.messages)
        decisions = result.decisions
    response, captured, attempt = invoke(tuple(messages))
    results.append(InvocationResult(captured, response, True, decisions, attempt))
    return tuple(results)


def build_initial_context(
    task: dict,
    condition: WorkflowCondition,
    data: dict,
    framework: str,
) -> tuple[Message, ...]:
    messages = [
        Message(
            "system",
            "You are a research agent. Answer using only the supplied context and tool results.",
        ),
        Message(
            "system",
            (
                "LangChain runtime: retrieved context, memory and tool observations "
                "are supplied as typed messages."
                if framework == "langchain"
                else "Custom ReAct runtime: use Thought, Action, Observation, then Final Answer."
            ),
            metadata={"source_type": "framework"},
        ),
    ]
    if condition.retrieval_top_k:
        messages.extend(build_retrieval_messages(task, condition, data["documents"]))
    if condition.include_memory:
        messages.extend(build_memory_messages(task, condition, data["memory"]))
    messages.append(Message("user", task["prompt"]))
    return tuple(messages)


def build_retrieval_messages(
    task: dict,
    condition: WorkflowCondition,
    documents: list[dict],
) -> list[Message]:
    relevant = [
        document
        for document in documents
        if task["task_id"] in document.get("relevant_task_ids", [])
    ]
    selected = relevant[: max(1, condition.retrieval_top_k)]
    messages = [document_message(document) for document in selected]
    if condition.duplicate_retrieval and messages:
        original = messages[0]
        messages.append(
            Message(
                original.role,
                original.content,
                metadata={**original.metadata, "bloat_labels": ("exact_duplicate",)},
            )
        )
    if condition.include_near_duplicate and relevant:
        document = relevant[0]
        messages.append(
            Message(
                "system",
                document.get("near_duplicate_text", document["text"]),
                metadata={
                    "source_type": "retrieval",
                    "source_id": f"{document['doc_id']}-near",
                    "relevance_score": 0.9,
                    "bloat_labels": ("near_duplicate",),
                },
            )
        )
    if condition.include_irrelevant_retrieval:
        irrelevant = next(
            (
                document
                for document in documents
                if task["task_id"] not in document.get("relevant_task_ids", [])
            ),
            None,
        )
        if irrelevant:
            messages.append(
                Message(
                    "system",
                    irrelevant["text"],
                    metadata={
                        "source_type": "retrieval",
                        "source_id": irrelevant["doc_id"],
                        "relevance_score": 0.0,
                        "bloat_labels": ("low_query_relevance",),
                    },
                )
            )
    return messages


def build_memory_messages(
    task: dict,
    condition: WorkflowCondition,
    memories: list[dict],
) -> list[Message]:
    relevant = [
        item for item in memories if task["task_id"] in item.get("relevant_task_ids", [])
    ]
    messages = [memory_message(item) for item in relevant[:1]]
    if condition.duplicate_memory and messages:
        original = messages[0]
        messages.append(
            Message(
                original.role,
                original.content,
                metadata={**original.metadata, "bloat_labels": ("exact_duplicate",)},
            )
        )
    if condition.include_near_duplicate and relevant:
        item = relevant[0]
        messages.append(
            Message(
                "system",
                item.get("near_duplicate_text", item["text"]),
                metadata={
                    "source_type": "memory",
                    "source_id": f"{item['memory_id']}-near",
                    "relevance_score": 0.9,
                    "bloat_labels": ("near_duplicate",),
                },
            )
        )
    if condition.include_stale_context:
        stale = next(
            (
                item
                for item in memories
                if task["task_id"] not in item.get("relevant_task_ids", [])
            ),
            None,
        )
        if stale:
            messages.append(
                Message(
                    "system",
                    stale["text"],
                    metadata={
                        "source_type": "memory",
                        "source_id": stale["memory_id"],
                        "relevance_score": 0.0,
                        "bloat_labels": ("low_query_relevance",),
                    },
                )
            )
    return messages


def document_message(document: dict) -> Message:
    return Message(
        "system",
        document["text"],
        metadata={
            "source_type": "retrieval",
            "source_id": document["doc_id"],
            "relevance_score": 1.0,
        },
    )


def memory_message(item: dict) -> Message:
    return Message(
        "system",
        item["text"],
        metadata={
            "source_type": "memory",
            "source_id": item["memory_id"],
            "relevance_score": 1.0,
        },
    )


def build_tool_message(task: dict, condition: WorkflowCondition) -> Message:
    tool = task["tool"]
    concise = f"{tool['name']} result: {tool['result']}"
    labels: tuple[str, ...] = ()
    content = concise
    if condition.verbose_tool_output:
        labels = ("verbose_tool_output",)
        detail = (
            " Diagnostic field confirms the calculation input was parsed and validated. "
            "The execution environment repeated provenance, formatting, timing, and "
            "intermediate metadata that are not required to answer the user."
        )
        content = concise + "\n" + detail * 8
    return Message(
        "system",
        content,
        metadata={
            "source_type": "tool",
            "source_id": tool["name"],
            "bloat_labels": labels,
        },
    )


def merge_labels(left: object, right: tuple[str, ...]) -> tuple[str, ...]:
    current = (left,) if isinstance(left, str) else tuple(left)
    return tuple(dict.fromkeys((*current, *right)))


def normalize_strategy(strategy: str) -> str:
    return {
        "exact_duplicate_removal": "exact",
        "source_aware": "source-aware",
        "combined": "source-aware",
    }.get(strategy, strategy)
