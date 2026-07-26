# Context Bloat Auditor

Engineering-grade runtime tracing, measurement, and mitigation toolkit for the
MSc thesis:

**Auditing and Controlling Context Bloat in LLM-Based Agents**

The system captures model-visible context, assigns provenance to context
segments, measures duplication and source dominance, applies auditable
mitigation policies, and stores every experiment in an immutable named run.

## Architecture

Production code uses a `src/` layout and explicit dependency boundaries:

```text
src/context_auditor/
  domain/        Immutable models, enums, text and privacy policies
  application/   Capture, analysis, mitigation and reporting use cases
  ports/         Provider, storage, tokenizer, clock and ID protocols
  adapters/      LangChain, DeepSeek, JSONL, datasets and run storage
  analytics/     Context-bloat metrics
  experiments/   Controlled workflows and experiment runner
  cli/           Command-line interface
```

Research material is separate from code:

```text
data/            Immutable, versioned datasets and annotations
configs/         Versioned experiment, provider and schema files
thesis/          Manuscript, literature, plans, materials and releases
tests/           Unit, integration and end-to-end tests
runs/            Generated experiment runs; never committed
```

Root-level files are limited to project metadata.

## Installation

Python 3.11 or 3.12 is required.

```powershell
python -m pip install -e ".[langchain,dev]"
```

## Controlled Pilot

Run the Custom ReAct pilot:

```powershell
context-auditor run `
  --config configs/experiments/pilot_custom_react_v1.json
```

Run both Custom ReAct and real LangChain integration paths:

```powershell
context-auditor run-suite
```

Each command creates a unique directory:

```text
runs/<experiment_id>/<utc>__<framework>__<model>__<dataset-version>__<git-sha>/
```

Existing run directories are never overwritten.

## Run Artifacts

Every run uses fixed artifact names:

```text
manifest.json
logs/run.log
traces/invocations.jsonl
metrics/invocations.csv
metrics/tasks.csv
reports/summary.json
reports/tables/
reports/figures/
```

The manifest records the project and schema versions, Git commit, Python and
LangChain versions, config and dataset hashes, model identity, seed,
repetition, status, output paths, and SHA-256 for every generated file.

## Privacy

`redacted` is the default trace mode. It masks email addresses, phone numbers,
Bearer tokens, API keys, authorization values, tokens, and secrets.

- `redacted`: stores analyzable text after masking.
- `hash-only`: stores stable content hashes without raw text.
- `full`: stores complete text and must only be used for controlled data.

Provider credentials are read from environment variables and are never written
to traces or manifests.

## DeepSeek Smoke Test

```powershell
$env:DEEPSEEK_API_KEY="..."
context-auditor check-provider --provider deepseek --model deepseek-v4-flash
context-auditor run-real-model-smoke --model deepseek-v4-flash
```

The smoke run stores provider token usage and latency in its named run.

## Tests

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

The suite covers domain policies, privacy, provenance, bloat metrics,
mitigation, run collision protection, UTF-8 text, immutable datasets, real
LangChain messages, named artifacts, and end-to-end experiment execution.

## Versioning

Current project and trace schema version: `1.0.0`.

The original pilot is preserved by the `v0.10.0-pilot-archive` Git tag and
[archived experiment package](thesis/releases/v0.10.0-pilot-artifacts.zip).
See [CHANGELOG.md](CHANGELOG.md) and
[architecture.md](thesis/engineering/architecture.md).
