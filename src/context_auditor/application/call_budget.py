"""Hard, append-only provider-invocation accounting."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid

from context_auditor.domain.models import (
    CallLedgerRecord,
    ModelRequestEnvelope,
    ProviderResponse,
)
from context_auditor.ports import ChatProvider


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def request_envelope_hash(request: ModelRequestEnvelope) -> str:
    payload = json.dumps(
        asdict(request),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class LedgerReservation:
    call_id: str
    call_index: int
    record: CallLedgerRecord


@dataclass
class CallBudget:
    limit: int = 500
    used: int = 0

    @property
    def remaining(self) -> int:
        return self.limit - self.used

    def reserve(
        self,
        request: ModelRequestEnvelope | None = None,
    ) -> LedgerReservation:
        if self.used >= self.limit:
            raise RuntimeError(
                f"Provider call budget exhausted ({self.used}/{self.limit})"
            )
        self.used += 1
        call_id = f"call-{self.used:04d}"
        record = ledger_record(request, call_id, self.used, "reserved", "reserved")
        return LedgerReservation(call_id, self.used, record)

    def complete(
        self,
        reservation: LedgerReservation,
        response: ProviderResponse,
    ) -> None:
        return None

    def fail(self, reservation: LedgerReservation, error: BaseException) -> None:
        return None


class BudgetedChatProvider:
    def __init__(
        self,
        provider: ChatProvider,
        budget: CallBudget | "PersistentCallBudget",
    ) -> None:
        self.provider = provider
        self.budget = budget
        self.provider_name = provider.provider_name
        self.model = provider.model

    def invoke(self, request: ModelRequestEnvelope) -> ProviderResponse:
        reservation = self.budget.reserve(request)
        try:
            response = self.provider.invoke(request)
        except BaseException as error:
            self.budget.fail(reservation, error)
            raise
        self.budget.complete(reservation, response)
        return response


class PersistentCallBudget:
    """Append-only JSONL ledger with one reservation per provider dispatch."""

    def __init__(
        self,
        path: str | Path,
        limit: int = 500,
        *,
        primary_limit: int = 480,
        retry_limit: int = 20,
    ) -> None:
        self.path = Path(path)
        self.limit = limit
        self.primary_limit = primary_limit
        self.retry_limit = retry_limit

    @property
    def used(self) -> int:
        return len(self.reservations())

    @property
    def remaining(self) -> int:
        return self.limit - self.used

    def reservations(self) -> dict[str, dict]:
        records: dict[str, dict] = {}
        if not self.path.is_file():
            return records
        for line_number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("event") == "reserved":
                records[str(item["call_id"])] = item
            elif "event" not in item:
                records[f"legacy-{line_number:04d}"] = item
        return records

    def outcomes(self) -> dict[str, dict]:
        result: dict[str, dict] = {}
        if not self.path.is_file():
            return result
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("event") in {"completed", "failed"}:
                result[str(item["call_id"])] = item
        return result

    def attempted_keys(self) -> set[tuple[str, str, int]]:
        return {
            (
                str(record.get("cell_id", "unspecified")),
                str(record.get("arm", "unmodified")),
                int(record.get("invocation_index", 0)),
            )
            for record in self.reservations().values()
        }

    def reserve(self, request: ModelRequestEnvelope) -> LedgerReservation:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with file_lock(self.path.with_suffix(self.path.suffix + ".lock")):
            used = len(self.reservations())
            index = used + 1
            if index > self.limit:
                raise RuntimeError(
                    f"Provider call budget exhausted ({used}/{self.limit})"
                )
            reservations = self.reservations()
            retry_of = request.metadata.get("retry_of")
            retry_count = sum(
                bool(item.get("retry_of")) for item in reservations.values()
            )
            primary_count = used - retry_count
            if retry_of:
                if retry_count >= self.retry_limit:
                    raise RuntimeError(
                        f"Manual retry budget exhausted "
                        f"({retry_count}/{self.retry_limit})"
                    )
                self._validate_retry_order(str(retry_of), reservations)
            if not retry_of and primary_count >= self.primary_limit:
                raise RuntimeError(
                    f"Primary provider-call budget exhausted "
                    f"({primary_count}/{self.primary_limit})"
                )
            call_id = f"call-{index:04d}-{uuid.uuid4().hex[:8]}"
            record = ledger_record(
                request,
                call_id,
                index,
                event="reserved",
                status="reserved",
            )
            self._append_unlocked(record)
        return LedgerReservation(call_id, index, record)

    def retryable_failures(self) -> list[dict]:
        reservations = self.reservations()
        outcomes = self.outcomes()
        retried = {
            str(item["retry_of"])
            for item in reservations.values()
            if item.get("retry_of")
        }
        eligible = []
        for call_id, reservation in reservations.items():
            outcome = outcomes.get(call_id)
            if (
                not reservation.get("retry_of")
                and call_id not in retried
                and outcome is not None
                and retryable_failure(outcome)
            ):
                eligible.append({**reservation, **outcome})
        return sorted(eligible, key=lambda item: int(item["call_index"]))

    def _validate_retry_order(
        self,
        retry_of: str,
        reservations: dict[str, dict],
    ) -> None:
        if retry_of not in reservations:
            raise ValueError(f"Retry source is not in the ledger: {retry_of}")
        eligible = self.retryable_failures()
        if not eligible:
            raise ValueError("The ledger has no retryable failed requests")
        expected = str(eligible[0]["call_id"])
        if retry_of != expected:
            raise ValueError(
                "Manual retries must follow original failed-ledger order: "
                f"expected {expected}, received {retry_of}"
            )

    def complete(
        self,
        reservation: LedgerReservation,
        response: ProviderResponse,
    ) -> None:
        payload_hash = (
            response.request_record.payload_sha256
            if response.request_record
            else reservation.record.request_sha256
        )
        record = CallLedgerRecord(
            **{
                **asdict(reservation.record),
                "event": "completed",
                "occurred_at": utc_now(),
                "request_sha256": payload_hash,
                "status": "completed",
            }
        )
        self._append(record)

    def fail(self, reservation: LedgerReservation, error: BaseException) -> None:
        status = getattr(error, "code", None)
        record = CallLedgerRecord(
            **{
                **asdict(reservation.record),
                "event": "failed",
                "occurred_at": utc_now(),
                "status": "failed",
                "error_type": type(error).__name__,
                "http_status": int(status) if isinstance(status, int) else None,
            }
        )
        self._append(record)

    def _append(self, record: CallLedgerRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with file_lock(self.path.with_suffix(self.path.suffix + ".lock")):
            self._append_unlocked(record)

    def _append_unlocked(self, record: CallLedgerRecord) -> None:
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def ledger_record(
    request: ModelRequestEnvelope | None,
    call_id: str,
    call_index: int,
    event: str,
    status: str,
) -> CallLedgerRecord:
    metadata = dict(request.metadata) if request else {}
    return CallLedgerRecord(
        event=event,
        call_id=call_id,
        call_index=call_index,
        occurred_at=utc_now(),
        cell_id=str(metadata.get("cell_id", "unspecified")),
        task_id=str(metadata.get("task_id", "unspecified")),
        framework=str(metadata.get("framework", "unspecified")),
        arm=str(metadata.get("arm", "unmodified")),
        invocation_index=int(metadata.get("provider_invocation_index", 0)),
        request_sha256=request_envelope_hash(request) if request else "",
        status=status,
        retry_of=(
            str(metadata["retry_of"]) if metadata.get("retry_of") else None
        ),
    )


def retryable_failure(record: dict) -> bool:
    status = record.get("http_status")
    if status == 429 or (isinstance(status, int) and 500 <= status <= 599):
        return True
    error_type = str(record.get("error_type") or "").lower()
    return "timeout" in error_type


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
