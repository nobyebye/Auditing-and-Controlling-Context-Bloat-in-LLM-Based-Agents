"""Stable enumerations used across the project."""

from enum import StrEnum


class SourceType(StrEnum):
    SYSTEM = "system"
    USER = "user"
    FRAMEWORK = "framework"
    RETRIEVAL = "retrieval"
    MEMORY = "memory"
    TOOL = "tool"
    TOOL_SCHEMA = "tool_schema"
    GENERATED_TRACE = "generated_trace"
    OTHER = "other"


class PrivacyMode(StrEnum):
    REDACTED = "redacted"
    FULL = "full"
    HASH_ONLY = "hash-only"


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
