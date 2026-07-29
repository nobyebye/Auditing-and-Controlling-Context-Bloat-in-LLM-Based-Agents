"""Natural retrieval, memory, and bounded tool workflows."""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, replace
from typing import Callable

from context_auditor.domain.models import (
    Message,
    ModelRequestEnvelope,
    ProviderResponse,
    ScoringResult,
    ToolDefinition,
)
from context_auditor.experiments.scoring import score_response

WORD_RE = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class NaturalInvocation:
    request: ModelRequestEnvelope
    response: ProviderResponse
    final: bool
    scoring: ScoringResult | None = None


def execute_natural_workflow(
    task: dict,
    *,
    framework: str,
    retrieval_top_k: int,
    memory_top_k: int,
    generation,
    max_provider_invocations_per_tool_cell: int,
    randomization_seed: int,
    invoke: Callable[[ModelRequestEnvelope], ProviderResponse],
    on_invocation: Callable[[NaturalInvocation], None] | None = None,
) -> tuple[NaturalInvocation, ...]:
    request = build_natural_request(
        task,
        framework=framework,
        retrieval_top_k=retrieval_top_k,
        memory_top_k=memory_top_k,
        generation=generation,
        randomization_seed=randomization_seed,
    )
    request = with_call_metadata(
        request,
        task=task,
        framework=framework,
        invocation_index=0,
    )
    response = invoke(request)
    if task["workflow_family"] != "multi_step_tool":
        scoring = score_response(task, response.content)
        invocation = NaturalInvocation(request, response, True, scoring)
        if on_invocation:
            on_invocation(invocation)
        return (invocation,)
    tool_scoring = score_tool_calls(task, response)
    if max_provider_invocations_per_tool_cell == 1 or not response.tool_calls:
        invocation = NaturalInvocation(request, response, True, tool_scoring)
        if on_invocation:
            on_invocation(invocation)
        return (invocation,)
    first = NaturalInvocation(request, response, False, None)
    if on_invocation:
        on_invocation(first)
    follow_up = build_tool_follow_up_request(
        request,
        task=task,
        framework=framework,
        tool_calls=response.tool_calls,
        assistant_content=response.content,
    )
    final_response = invoke(follow_up)
    if final_response.dispatch_error_type:
        tool_scoring = replace(
            tool_scoring,
            success=False,
            score=0.0,
            details={
                **tool_scoring.details,
                "termination_reason": "provider_dispatch_failed",
                "error_type": final_response.dispatch_error_type,
            },
        )
    elif final_response.tool_calls:
        tool_scoring = replace(
            tool_scoring,
            success=False,
            score=0.0,
            details={
                **tool_scoring.details,
                "termination_reason": (
                    "provider_invocation_cap_reached_before_third_dispatch"
                ),
            },
        )
    final = NaturalInvocation(follow_up, final_response, True, tool_scoring)
    if on_invocation:
        on_invocation(final)
    return (first, final)


def build_tool_follow_up_request(
    request: ModelRequestEnvelope,
    *,
    task: dict,
    framework: str,
    tool_calls: tuple,
    assistant_content: str = "",
) -> ModelRequestEnvelope:
    follow_up_messages = [
        *request.messages,
        Message(
            "assistant",
            assistant_content or "[tool call]",
            metadata={"source_type": "generated_trace"},
            tool_calls=tuple(tool_calls),
        ),
    ]
    for call in tool_calls:
        follow_up_messages.append(
            Message(
                "tool",
                deterministic_tool_observation(task, call.name, call.arguments),
                name=call.name,
                metadata={
                    "source_type": "tool",
                    "source_id": call.call_id or call.name,
                },
                tool_call_id=call.call_id,
            )
        )
    follow_up_messages.append(
        Message(
            "system",
            "Use the tool observations to provide the final response.",
            metadata={"source_type": "framework"},
        )
    )
    return with_call_metadata(
        replace(request, messages=tuple(follow_up_messages)),
        task=task,
        framework=framework,
        invocation_index=1,
    )


def build_natural_request(
    task: dict,
    *,
    framework: str,
    retrieval_top_k: int,
    memory_top_k: int,
    generation,
    randomization_seed: int | None = None,
) -> ModelRequestEnvelope:
    messages = [
        Message(
            "system",
            "Complete the task using only the context and tools supplied.",
        ),
        Message(
            "system",
            (
                "Context is assembled by a LangChain execution path."
                if framework == "langchain"
                else "Context is assembled by a custom ReAct execution path."
            ),
            metadata={"source_type": "framework"},
        ),
    ]
    workflow = task["workflow_family"]
    if workflow == "retrieval_qa":
        for rank, item in enumerate(
            retrieve(task["prompt"], task.get("documents", []), retrieval_top_k),
            start=1,
        ):
            messages.append(
                Message(
                    "system",
                    f"{item.get('title', item['source_id'])}\n{item['text']}",
                    metadata={
                        "source_type": "retrieval",
                        "source_id": item["source_id"],
                        "retrieval_rank": rank,
                        "relevance_score": lexical_score(
                            task["prompt"], item["text"]
                        ),
                    },
                )
            )
    elif workflow == "memory_turns":
        for rank, item in enumerate(
            retrieve(
                task["prompt"],
                task.get("memory_sessions", []),
                memory_top_k,
            ),
            start=1,
        ):
            messages.append(
                Message(
                    "system",
                    f"[{item.get('date') or 'unknown date'}]\n{item['text']}",
                    metadata={
                        "source_type": "memory",
                        "source_id": item["source_id"],
                        "memory_rank": rank,
                        "relevance_score": lexical_score(
                            task["prompt"], item["text"]
                        ),
                    },
                )
            )
    messages.append(Message("user", task["prompt"]))
    tools = tuple(
        ToolDefinition(
            name=item["name"],
            description=item.get("description", ""),
            parameters=item.get("parameters", {}),
        )
        for item in task.get("tools", [])
        if item.get("name")
    )
    return ModelRequestEnvelope(
        messages=tuple(messages),
        tools=tools,
        generation_parameters=generation,
        randomization_seed=randomization_seed,
        provider_seed=None,
        metadata={
            "source_dataset": task.get("source_dataset"),
            "source_record_id": task.get("source_record_id"),
        },
    )


def with_call_metadata(
    request: ModelRequestEnvelope,
    *,
    task: dict,
    framework: str,
    invocation_index: int,
) -> ModelRequestEnvelope:
    cell_id = f"{task['task_id']}__{framework}"
    return replace(
        request,
        metadata={
            **request.metadata,
            "cell_id": cell_id,
            "task_id": task["task_id"],
            "framework": framework,
            "arm": "natural_unmodified",
            "provider_invocation_index": invocation_index,
        },
    )


def retrieve(query: str, items: list[dict], top_k: int) -> list[dict]:
    return sorted(
        items,
        key=lambda item: (
            -lexical_score(query, str(item.get("text", ""))),
            str(item.get("source_id", "")),
        ),
    )[:top_k]


def lexical_score(left: str, right: str) -> float:
    left_tokens = set(WORD_RE.findall(left.casefold()))
    right_tokens = set(WORD_RE.findall(right.casefold()))
    return len(left_tokens & right_tokens) / len(left_tokens) if left_tokens else 0.0


def score_tool_calls(task: dict, response: ProviderResponse) -> ScoringResult:
    parameter_names = {
        str(tool.get("name", "")): tuple(
            str(name)
            for name in tool.get("parameters", {}).get(
                "required",
                tool.get("parameters", {}).get("properties", {}).keys(),
            )
        )
        for tool in task.get("tools", [])
    }
    expected = canonical_tool_calls(
        task.get("expected_tool_calls", []),
        parameter_names=parameter_names,
    )
    observed = canonical_tool_calls(
        [
            {"name": call.name, "arguments": dict(call.arguments)}
            for call in response.tool_calls
        ]
    )
    success = observed == expected and bool(expected)
    return ScoringResult(
        success=success,
        score=1.0 if success else 0.0,
        method="bfcl_tool_call_exact",
        normalized_output=json.dumps(observed, sort_keys=True),
        normalized_expected=json.dumps(expected, sort_keys=True),
    )


def canonical_tool_calls(
    value,
    *,
    parameter_names: dict[str, tuple[str, ...]] | None = None,
) -> list[dict]:
    calls = flatten_tool_calls(value)
    normalized = []
    for item in calls:
        if isinstance(item, str):
            name = bfcl_expression_name(item)
            parsed = parse_bfcl_call(
                item,
                positional_names=(parameter_names or {}).get(name, ()),
            )
            if parsed is not None:
                normalized.append(parsed)
            continue
        if not isinstance(item, dict):
            continue
        if len(item) == 1 and "name" not in item:
            name, arguments = next(iter(item.items()))
        else:
            function = item.get("function", item)
            name = function.get("name")
            arguments = function.get(
                "arguments",
                item.get("arguments", {}),
            )
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {"raw": arguments}
        normalized.append(
            {
                "name": str(name or ""),
                "arguments": arguments if isinstance(arguments, dict) else {},
            }
        )
    return sorted(
        normalized,
        key=lambda item: (item["name"], json.dumps(item["arguments"], sort_keys=True)),
    )


def flatten_tool_calls(value) -> list:
    if not isinstance(value, list):
        return [value]
    flattened = []
    for item in value:
        if isinstance(item, list):
            flattened.extend(flatten_tool_calls(item))
        else:
            flattened.append(item)
    return flattened


def parse_bfcl_call(
    value: str,
    *,
    positional_names: tuple[str, ...] = (),
) -> dict | None:
    try:
        expression = ast.parse(value.strip(), mode="eval").body
    except (SyntaxError, ValueError):
        return None
    if not isinstance(expression, ast.Call):
        return None
    if isinstance(expression.func, ast.Name):
        name = expression.func.id
    elif isinstance(expression.func, ast.Attribute):
        name = expression.func.attr
    else:
        return None
    arguments = {}
    for index, argument in enumerate(expression.args):
        argument_name = (
            positional_names[index]
            if index < len(positional_names)
            else f"arg{index}"
        )
        try:
            arguments[argument_name] = ast.literal_eval(argument)
        except (ValueError, TypeError):
            arguments[argument_name] = ast.unparse(argument)
    for keyword in expression.keywords:
        if keyword.arg is None:
            continue
        try:
            arguments[keyword.arg] = ast.literal_eval(keyword.value)
        except (ValueError, TypeError):
            arguments[keyword.arg] = ast.unparse(keyword.value)
    return {"name": name, "arguments": arguments}


def bfcl_expression_name(value: str) -> str:
    match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", value)
    return match.group(1) if match else ""


def deterministic_tool_observation(
    task: dict,
    name: str,
    arguments: dict,
) -> str:
    fixtures = task.get("tool_results", {})
    if name in fixtures:
        return json.dumps(fixtures[name], ensure_ascii=False, sort_keys=True)
    return json.dumps(
        {
            "status": "executed_for_evaluation",
            "tool": name,
            "arguments": arguments,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
