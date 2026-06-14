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
- Deterministic local retrieval for reproducible RAG-style experiments.
- Near-duplicate and irrelevant-context mitigation strategies.
- Pre-call message-level mitigation for controlled before/after rerun
  configurations.
- Online guard flags for growth spikes, duplicate segments, and source
  dominance.
- Conservative mitigation report for exact duplicate retrieval, memory, and
  tool segments.
- Controlled custom ReAct-style pilot workflows for retrieval, memory, and
  tool-use experiments.
- LangChain-compatible pilot workflows that exercise the callback
  instrumentation boundary.
- One-command experiment suite that runs both implementations and writes
  cross-framework comparison tables.
- File-backed controlled datasets for reproducible thesis experiments.
- Minimal provider abstraction for mock and OpenAI-compatible chat providers.
- Optional LangChain callback adapter.

## Repository Layout

```text
context_auditor/     Core package
datasets/           Controlled JSON datasets used by the pilot experiments
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

Run the LangChain-compatible pilot experiment:

```powershell
python -m context_auditor.cli run-langchain-pilot --config configs/langchain_pilot.json --out traces/langchain_pilot.jsonl
```

Analyze traces:

```powershell
python -m context_auditor.cli analyze traces/pilot.jsonl --out results/pilot_summary.json --tables-dir results/tables --charts-dir results/charts
python -m context_auditor.cli analyze traces/langchain_pilot.jsonl --out results/langchain_pilot_summary.json --tables-dir results/langchain_tables --charts-dir results/langchain_charts
```

Run the full thesis experiment suite:

```powershell
python -m context_auditor.cli run-suite --out-dir artifacts
```

Generate a mitigation report:

```powershell
python -m context_auditor.cli mitigate traces/pilot.jsonl --out results/mitigation_report.json --csv-out results/tables/mitigation_report.csv
```

Run tests:

```powershell
python -m unittest discover -s tests
```

## Controlled Dataset

The default pilot uses `datasets/controlled_synthetic/`, which contains:

- `tasks.json`: retrieval, memory, and tool-use tasks with expected keywords
- `policy_docs.json`: local policy documents for deterministic retrieval
- `memory_items.json`: controlled memory/history items

Keeping the dataset in JSON makes the experimental material easy to inspect,
version, and replace for the full thesis study.

## Provider Abstraction

The pilot defaults to the deterministic `mock` provider so experiments can be
run without API cost. A minimal OpenAI-compatible provider is available for
future real-model runs through:

```powershell
$env:OPENAI_COMPATIBLE_API_KEY="..."
$env:OPENAI_COMPATIBLE_BASE_URL="https://api.openai.com/v1"
```

## Installable CLI

From the repository root:

```powershell
pip install -e .
context-auditor run-pilot --out traces/pilot.jsonl
context-auditor run-langchain-pilot --out traces/langchain_pilot.jsonl
context-auditor run-suite --out-dir artifacts
context-auditor analyze traces/pilot.jsonl --out results/pilot_summary.json --tables-dir results/tables --charts-dir results/charts
context-auditor analyze traces/langchain_pilot.jsonl --out results/langchain_pilot_summary.json --tables-dir results/langchain_tables --charts-dir results/langchain_charts
context-auditor mitigate traces/pilot.jsonl --out results/mitigation_report.json --csv-out results/tables/mitigation_report.csv
```

## Experiment Outputs

The commands produce:

- `traces/pilot.jsonl`: per-invocation model-visible context traces
- `traces/langchain_pilot.jsonl`: LangChain-compatible pilot traces
- `results/pilot_summary.json`: grouped bloat metrics
- `results/tables/*.csv`: thesis-ready summary tables
- `results/charts/*.svg`: first-pass figures for redundancy and token counts
- `results/mitigation_report.json`: before/after mitigation evaluation report
- `results/tables/mitigation_report.csv`: thesis-ready mitigation table
- `artifacts/results/framework_comparison.json`: cross-framework comparison
  data for custom ReAct and LangChain-compatible runs
- `artifacts/results/framework_comparison.csv`: thesis-ready cross-framework
  comparison table
- `artifacts/results/mitigation_report.json` and
  `artifacts/results/langchain_mitigation_report.json`: mitigation reports for
  both framework runs

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

The project uses semantic versioning. Current version: `0.8.0`.

See [CHANGELOG.md](CHANGELOG.md) for changes and
[docs/architecture.md](docs/architecture.md) for the package structure.
