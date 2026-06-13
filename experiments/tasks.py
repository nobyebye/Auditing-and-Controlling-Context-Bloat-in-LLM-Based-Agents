"""Controlled task definitions for pilot experiments."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    task_id: str
    workflow_family: str
    prompt: str
    expected_keyword: str


RETRIEVAL_TASKS = [
    Task("retrieval-001", "retrieval_qa", "Which policy covers remote work eligibility?", "remote"),
    Task("retrieval-002", "retrieval_qa", "What must employees do before using external AI tools?", "approval"),
    Task("retrieval-003", "retrieval_qa", "How long are incident records retained?", "retained"),
]

TOOL_TASKS = [
    Task("tool-001", "multi_step_tool", "Calculate 18 * 7, then add 42.", "168"),
    Task("tool-002", "multi_step_tool", "Calculate 125 / 5, then subtract 9.", "16"),
    Task("tool-003", "multi_step_tool", "Calculate 14 * 14, then add 4.", "200"),
]

MEMORY_TASKS = [
    Task("memory-001", "memory_turns", "Use the remembered project name in the answer.", "context"),
    Task("memory-002", "memory_turns", "Use the remembered supervisor preference in the answer.", "auditing"),
    Task("memory-003", "memory_turns", "Use the remembered thesis constraint in the answer.", "lightweight"),
]

ALL_TASKS = RETRIEVAL_TASKS + TOOL_TASKS + MEMORY_TASKS


POLICY_DOCS = [
    "Remote work eligibility is covered by the Flexible Work Policy. Employees need manager approval.",
    "External AI tools require project owner approval before confidential data may be entered.",
    "Incident records are retained for two years after closure unless legal review requires longer retention.",
]

MEMORY_ITEMS = [
    "Project name: Runtime Context Auditor.",
    "Supervisor preference: keep the thesis centered on auditing, not broad optimization.",
    "Thesis constraint: mitigation should remain lightweight and secondary.",
]
