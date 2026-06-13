"""Lightweight context growth guard."""

from __future__ import annotations

from dataclasses import dataclass

from .schema import AuditTrace


@dataclass(frozen=True)
class GuardConfig:
    growth_spike_ratio: float = 1.5
    source_dominance_ratio: float = 0.6
    min_growth_tokens: int = 50
    watched_duplicate_sources: tuple[str, ...] = ("retrieval", "tool")


class ContextGrowthGuard:
    def __init__(self, config: GuardConfig | None = None) -> None:
        self.config = config or GuardConfig()
        self._previous_tokens_by_task: dict[str, int] = {}

    def evaluate(self, trace: AuditTrace) -> list[str]:
        flags: list[str] = []
        total_tokens = int(trace.metrics.get("total_tokens", 0))
        previous_tokens = self._previous_tokens_by_task.get(trace.task_id)

        if previous_tokens is not None:
            growth = total_tokens - previous_tokens
            if (
                previous_tokens > 0
                and growth >= self.config.min_growth_tokens
                and total_tokens / previous_tokens >= self.config.growth_spike_ratio
            ):
                flags.append("growth_spike")

        for source, ratio in trace.metrics.get("source_ratios", {}).items():
            if ratio >= self.config.source_dominance_ratio:
                flags.append(f"source_dominance:{source}")

        seen: dict[str, str] = {}
        for segment in trace.segments:
            if segment.source_type not in self.config.watched_duplicate_sources:
                continue
            previous_source = seen.get(segment.normalized_hash)
            if previous_source == segment.source_type:
                flags.append(f"duplicate_{segment.source_type}")
                break
            seen[segment.normalized_hash] = segment.source_type

        if trace.metrics.get("duplicate_segment_count", 0):
            flags.append("duplicate_segments")

        self._previous_tokens_by_task[trace.task_id] = total_tokens
        return sorted(set(flags))
