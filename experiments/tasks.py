"""Controlled task definitions for pilot experiments."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    task_id: str
    workflow_family: str
    prompt: str
    expected_keyword: str
