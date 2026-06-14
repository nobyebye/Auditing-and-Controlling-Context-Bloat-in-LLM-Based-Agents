# Architecture

This project is organized around one thesis problem: context bloat in
LLM-based agents.

## Core Package

- `context_auditor.schema`: public dataclasses for messages, segments, and
  invocation traces.
- `context_auditor.provenance`: rule-based source labeling for model-visible
  context.
- `context_auditor.metrics`: token, character, redundancy, uniqueness, source,
  and cost-proxy metrics.
- `context_auditor.guard`: online risk flags for growth spikes, source
  dominance, and duplicate segments.
- `context_auditor.bloat`: offline bloat classification and grouped summaries.
- `context_auditor.framework_compare`: cross-framework summary comparison and
  CSV export helpers.
- `context_auditor.mitigation`: conservative duplicate-removal mitigation
  utilities.
- `context_auditor.message_mitigation`: pre-call message-level mitigation for
  controlled rerun configurations.
- `context_auditor.mitigation_eval`: before/after mitigation evaluation over
  final task invocations.
- `context_auditor.providers`: mock and OpenAI-compatible chat provider
  abstraction for future real-model experiment runs.
- `context_auditor.text_similarity`: deterministic token overlap and Jaccard
  helpers.
- `context_auditor.evaluation`: lightweight task success evaluation.
- `context_auditor.reporting`: CSV and SVG reporting helpers for thesis tables
  and figures.
- `context_auditor.tracer`: runtime capture API used before LLM invocations.
- `context_auditor.langchain_adapter`: optional LangChain callback adapter.
- `context_auditor.cli`: command-line interface.

## Experiment Layer

- `datasets/controlled_synthetic`: JSON task, retrieval corpus, and memory
  inputs for reproducible pilot runs.
- `experiments.datasets`: dataset loader that materializes JSON files into
  task, document, and memory objects.
- `experiments.config`: JSON experiment matrix loader.
- `experiments.custom_react`: controlled ReAct-style workflow implementation.
- `experiments.langchain_pilot`: LangChain-compatible workflow implementation
  that uses the callback adapter and falls back to local message objects when
  `langchain_core` is not installed.
- `experiments.retrieval`: deterministic local retrieval utilities.
- `experiments.pilot`: custom ReAct orchestration entry point used by the CLI.
- `experiments.suite`: end-to-end orchestration for custom ReAct,
  LangChain-compatible, summary, chart, and framework comparison outputs.

## Data Flow

1. Agent code constructs model-visible messages.
2. `RuntimeAuditor.capture()` receives those messages before the model call.
3. Messages are segmented and labeled by provenance source.
4. Metrics and guard flags are attached to the invocation trace.
5. JSONL traces are analyzed offline for bloat patterns and mitigation effects.

## Versioning Policy

The artifact uses semantic versioning:

- Patch version: bug fixes, documentation, or test-only changes.
- Minor version: new metrics, CLI commands, adapters, or experiment workflows.
- Major version: incompatible trace schema or public API changes.

Current version: `0.8.0`.
