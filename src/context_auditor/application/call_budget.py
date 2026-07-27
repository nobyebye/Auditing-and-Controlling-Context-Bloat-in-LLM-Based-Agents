"""Hard provider-call accounting for paid validation studies."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from context_auditor.domain.models import ModelRequestEnvelope, ProviderResponse
from context_auditor.ports import ChatProvider


@dataclass
class CallBudget:
    limit: int = 500
    used: int = 0

    @property
    def remaining(self) -> int:
        return self.limit - self.used

    def reserve(self) -> int:
        if self.used >= self.limit:
            raise RuntimeError(
                f"Provider call budget exhausted ({self.used}/{self.limit})"
            )
        self.used += 1
        return self.used


class BudgetedChatProvider:
    def __init__(self, provider: ChatProvider, budget: CallBudget) -> None:
        self.provider = provider
        self.budget = budget
        self.provider_name = provider.provider_name
        self.model = provider.model

    def invoke(self, request: ModelRequestEnvelope) -> ProviderResponse:
        self.budget.reserve()
        return self.provider.invoke(request)


class PersistentCallBudget:
    def __init__(self, path: str | Path, limit: int = 500) -> None:
        self.path = Path(path)
        self.limit = limit

    @property
    def used(self) -> int:
        return self._used_unlocked()

    def _used_unlocked(self) -> int:
        if not self.path.is_file():
            return 0
        return sum(
            1
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )

    @property
    def remaining(self) -> int:
        return self.limit - self.used

    def reserve(self) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with file_lock(self.path.with_suffix(self.path.suffix + ".lock")):
            used = self._used_unlocked()
            index = used + 1
            if index > self.limit:
                raise RuntimeError(
                    f"Provider call budget exhausted ({used}/{self.limit})"
                )
            entry = {
                "call_index": index,
                "reserved_at": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            }
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        return index


@contextmanager
def file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
