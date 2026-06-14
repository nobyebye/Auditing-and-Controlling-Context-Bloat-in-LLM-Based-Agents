"""Runtime auditing toolkit for automatically constructed LLM-agent context."""

from ._version import __version__
from .bloat import BloatThresholds, classify_bloat, summarize_traces
from .guard import GuardConfig, ContextGrowthGuard
from .io import load_jsonl, write_jsonl
from .mitigation import MitigationReport, remove_exact_duplicate_segments
from .mitigation_eval import evaluate_mitigation_strategies, final_invocations, summarize_mitigation_rows
from .provenance import SourceType, label_message_source, segment_messages
from .providers import ChatProvider, MockChatProvider, OpenAICompatibleChatProvider, provider_from_environment
from .schema import AuditTrace, Message, Segment
from .tracer import RuntimeAuditor, TraceMetadata

__all__ = [
    "AuditTrace",
    "BloatThresholds",
    "ChatProvider",
    "ContextGrowthGuard",
    "GuardConfig",
    "Message",
    "MitigationReport",
    "MockChatProvider",
    "OpenAICompatibleChatProvider",
    "RuntimeAuditor",
    "Segment",
    "SourceType",
    "TraceMetadata",
    "__version__",
    "classify_bloat",
    "label_message_source",
    "load_jsonl",
    "evaluate_mitigation_strategies",
    "final_invocations",
    "provider_from_environment",
    "remove_exact_duplicate_segments",
    "segment_messages",
    "summarize_mitigation_rows",
    "summarize_traces",
    "write_jsonl",
]
