"""Small real-provider smoke test for validating API connectivity."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from context_auditor import Message, RuntimeAuditor, TraceMetadata, provider_from_environment


def run_real_model_smoke(
    trace_path: str | Path = "traces/real_model_smoke.jsonl",
    report_path: str | Path = "results/real_model_smoke_report.json",
    provider_name: str = "deepseek",
    model: str = "deepseek-v4-flash",
    prompt: str = "Answer in one short sentence: what is context bloat in an LLM agent?",
) -> dict[str, object]:
    trace_output = Path(trace_path)
    report_output = Path(report_path)
    if trace_output.exists():
        trace_output.unlink()

    messages = [
        Message(role="system", content="You are a concise research assistant for an LLM-agent thesis."),
        Message(role="user", content=prompt),
    ]
    auditor = RuntimeAuditor(trace_output)
    metadata = TraceMetadata(
        task_id="real-model-smoke-001",
        framework="real-model-smoke",
        provider=provider_name,
        model=model,
        configuration="single_call",
        workflow_family="real_model_smoke",
        experiment_id=f"{provider_name}-real-model-smoke",
        run_id="run-001",
        dataset_name="manual_smoke",
    )
    trace = auditor.capture(metadata, messages)

    provider = provider_from_environment(provider_name, model)
    response = provider.complete(messages)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": provider_name,
        "model": model,
        "trace_path": str(trace_output),
        "trace_id": trace.trace_id,
        "response_char_count": len(response),
        "response_preview": response[:500],
    }
    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
