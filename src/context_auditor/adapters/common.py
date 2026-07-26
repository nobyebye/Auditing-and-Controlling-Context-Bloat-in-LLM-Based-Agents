"""Default clock, ID, and tokenizer adapters."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import uuid4

TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)
RUN_COMPONENT_RE = re.compile(r"[^a-z0-9._-]+")
RUN_ID_RE = re.compile(
    r"^\d{8}T\d{6}Z__[a-z0-9._-]+__[a-z0-9._-]+__[a-z0-9._-]+__[a-f0-9]{7,40}$"
)


class UtcClock:
    def now_iso(self) -> str:
        return datetime.now(UTC).isoformat()


class RegexTokenizer:
    name = "regex-unicode-v1"

    def count(self, text: str) -> int:
        return len(TOKEN_RE.findall(text)) if text else 0


class DefaultIdGenerator:
    def new_trace_id(self) -> str:
        return str(uuid4())

    def new_run_id(
        self,
        framework: str,
        model: str,
        dataset_version: str,
        git_commit: str,
    ) -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        parts = (
            timestamp,
            slug(framework),
            slug(model),
            slug(dataset_version),
            git_commit.casefold()[:8],
        )
        run_id = "__".join(parts)
        validate_run_id(run_id)
        return run_id


def slug(value: str) -> str:
    normalized = RUN_COMPONENT_RE.sub("-", value.strip().casefold()).strip("-")
    if not normalized:
        raise ValueError("Run identifier components cannot be empty")
    return normalized


def validate_run_id(run_id: str) -> None:
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError(
            "run_id must use UTC timestamp, framework, model, dataset version, and Git SHA"
        )
