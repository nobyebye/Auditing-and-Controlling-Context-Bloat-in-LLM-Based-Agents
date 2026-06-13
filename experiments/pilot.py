"""Pilot experiment runner."""

from __future__ import annotations

from pathlib import Path

from context_auditor import RuntimeAuditor

from .custom_react import AgentConfig, CustomReactAgent
from .tasks import MEMORY_TASKS, RETRIEVAL_TASKS, TOOL_TASKS


def run_pilot(output_path: str | Path) -> None:
    output = Path(output_path)
    if output.exists():
        output.unlink()
    auditor = RuntimeAuditor(output)
    agent = CustomReactAgent(auditor)

    configs = [
        AgentConfig("baseline"),
        AgentConfig("retrieval_top1", retrieval_top_k=1),
        AgentConfig("retrieval_top3", retrieval_top_k=3),
        AgentConfig("retrieval_duplicate", retrieval_top_k=2, duplicate_retrieval=True),
        AgentConfig("memory_full", include_memory=True),
        AgentConfig("memory_duplicate", include_memory=True, duplicate_memory=True),
        AgentConfig("tool_use", use_tools=True),
        AgentConfig("tool_repeated_output", use_tools=True, repeat_tool_output=True),
        AgentConfig("retrieval_memory_tool", retrieval_top_k=3, include_memory=True, use_tools=True),
    ]

    for task in RETRIEVAL_TASKS:
        for config in (configs[0], configs[1], configs[2], configs[3]):
            agent.run(task, config)

    for task in MEMORY_TASKS:
        for config in (configs[0], configs[4], configs[5]):
            agent.run(task, config)

    for task in TOOL_TASKS:
        for config in (configs[0], configs[6], configs[7], configs[8]):
            agent.run(task, config)
