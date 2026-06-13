# Context Bloat Auditor

Runtime tracing, measurement, and mitigation toolkit for context bloat in
LLM-based agents.

This repository supports the MSc thesis direction:

**Auditing and Controlling Context Bloat in LLM-Based Agents**

The broader object of study is automatically constructed context: model-visible
messages assembled from system prompts, user input, retrieval, memory,
conversation history, tool traces, and framework-generated content. The central
research problem is context bloat: redundant, stale, irrelevant, repeated, or
oversized context that increases cost and can make agent behavior harder to
debug.

## Features

- Runtime capture of model-visible messages before each LLM invocation.
- Framework-agnostic provenance labels for system, user, framework, retrieval,
  memory, tool, generated trace, and other context.
- Context bloat metrics:
  - Redundancy Ratio
  - Unique Information Ratio
  - Context Growth Rate
  - Source Contribution Ratio
  - Duplicate Segment Count
  - Source Dominance
  - Estimated Cost Proxy
- Online guard flags for growth spikes, duplicate segments, and source
  dominance.
- Conservative mitigation report for exact duplicate retrieval, memory, and
  tool segments.
- Controlled custom ReAct-style pilot workflows for retrieval, memory, and
  tool-use experiments.
- Optional LangChain callback adapter.

## Repository Layout

```text
context_auditor/     Core package
experiments/         Controlled pilot workflows and tasks
scripts/             Backward-compatible helper scripts and DOCX builders
docs/                Thesis proposal, chapter outline, protocol, architecture
tests/               Unit tests
```

## Quick Start

Run the pilot experiment:

```powershell
python -m context_auditor.cli run-pilot --config configs/pilot.json --out traces/pilot.jsonl
```

Analyze traces:

```powershell
python -m context_auditor.cli analyze traces/pilot.jsonl --out results/pilot_summary.json --tables-dir results/tables --charts-dir results/charts
```

Generate a mitigation report:

```powershell
python -m context_auditor.cli mitigate traces/pilot.jsonl --out results/mitigation_report.json
```

Run tests:

```powershell
python -m unittest discover -s tests
```

## Installable CLI

From the repository root:

```powershell
pip install -e .
context-auditor run-pilot --out traces/pilot.jsonl
context-auditor analyze traces/pilot.jsonl --out results/pilot_summary.json --tables-dir results/tables --charts-dir results/charts
context-auditor mitigate traces/pilot.jsonl --out results/mitigation_report.json
```

## Experiment Outputs

The pilot produces:

- `traces/pilot.jsonl`: per-invocation model-visible context traces
- `results/pilot_summary.json`: grouped bloat metrics
- `results/tables/*.csv`: thesis-ready summary tables
- `results/charts/*.svg`: first-pass figures for redundancy and token counts
- `results/mitigation_report.json`: duplicate-removal token reduction report

## Trace Schema

Each JSONL row represents one LLM invocation and includes:

- task metadata: `schema_version`, `experiment_id`, `run_id`, `trace_id`,
  `task_id`, `framework`, `provider`, `model`, `configuration`,
  `config_hash`, `dataset_name`, `workflow_family`, `invocation_index`,
  `timestamp`
- raw `messages`
- provenance-labeled `segments`
- aggregate `metrics`
- `task_success`, `task_output`, and `risk_flags`

The schema is intentionally framework-agnostic so the same analysis can be used
for LangChain callbacks, a custom ReAct loop, or other agent implementations.

## Versioning

The project uses semantic versioning. Current version: `0.3.0`.

See [CHANGELOG.md](CHANGELOG.md) for changes and
[docs/architecture.md](docs/architecture.md) for the package structure.
