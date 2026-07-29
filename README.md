# Context Bloat Auditor

Engineering-grade runtime tracing, measurement, and mitigation toolkit for the
MSc thesis:

**Runtime Auditing of Context Bloat in LLM-Based Agents: Detection,
Measurement, and Mitigation Evaluation**

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

## Formal Study

The frozen benchmark contains 6 calibration tasks and 30 held-out test tasks.
Run the primary DeepSeek matrix only from a clean Git worktree:

```powershell
python -m context_auditor.cli run-formal-suite `
  --custom-config configs/experiments/formal_custom_react_deepseek_v1.json `
  --langchain-config configs/experiments/formal_langchain_deepseek_v1.json `
  --project-root . `
  --confirm-real-cost
```

The runner refuses a real-provider formal run when tracked or untracked source
changes are present. See
[the frozen protocol](thesis/plans/experiment_protocol.md) and
[the 2026-07-26 run record](thesis/releases/v1.1.0-formal-study-run.md).

This schema-1.1 study is retained as **Study A**, a controlled perturbation
benchmark. Its injected labels establish pipeline consistency, not external
detection accuracy.

## Independent Validation

Schema 1.2.1 adds two independent evidence stages:

- **Study B** captures natural requests from 60 held-out tasks sampled from
  HotpotQA, LongMemEval, and BFCL v4, then evaluates heuristic indicators
  against two independent context annotations.
- **Study C** replays one-segment counterfactual removals and compares
  provenance-aware mitigation with an equal-budget LLMLingua-2 arm. Mitigation
  outcomes receive a separate condition-blind human review.

Real calibration and held-out runs use a three-stage OSF evidence chain in
`thesis/plans/osf_registration_manifest_v1.2.1.json`. The initial registration
and a prospective calibration-method clarification must both validate before
calibration. A post-calibration addendum must then freeze the final codebook,
detector settings, configs, and dependency hashes before held-out calls.

Prepare and calibrate the external dataset without provider cost:

```powershell
context-auditor prepare-external-dataset `
  --hotpot data/sources/hotpot_dev_distractor_v1.json `
  --longmemeval data/sources/longmemeval_s_cleaned.json `
  --bfcl data/sources/bfcl_v4_multi_turn_base_first_two.jsonl

context-auditor freeze-external-protocol `
  --phase clarification `
  --output thesis/releases/osf_calibration_method_clarification_v1.2.1.zip
```

Upload the clarification ZIP to an immutable public OSF registration and
record its URL, timestamp, package hash, release tag, and release commit.
Authorization is derived from cryptographic validation; editable boolean flags
do not open the gate. Run four calibration tasks per workflow through both
frameworks, export annotations with an explicit
`--include-split calibration`, and select thresholds with
`calibrate-detector`. Register the frozen codebook and calibration addendum
before using `--include-split test` or issuing held-out calls. Study C performs
at most 108 counterfactual requests and exactly 180 single-request mitigation
replays. Its primary ITT table retains every dispatched request. The shared
ledger reserves 480 primary requests and 20 ordered manual retries, and refuses
request 501 before dispatch. The frozen design is in
[external_validation_protocol_v1.2.1.md](thesis/plans/external_validation_protocol_v1.2.1.md).

## Run Artifacts

Every run uses fixed artifact names:

```text
manifest.json
logs/run.log
traces/invocations.jsonl
metrics/invocations.csv
metrics/tasks.csv
reports/summary.json
reports/rq_evidence.json
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
python -m pytest -q
```

The suite covers domain policies, privacy, provenance, bloat metrics,
mitigation, run collision protection, UTF-8 text, immutable datasets, real
LangChain messages, named artifacts, and end-to-end experiment execution.

## Versioning

Current project and trace schema version: `1.2.1`. Schemas `1.1.0` and `1.2.0`
remain readable for archived evidence but are not written by current code.

The original pilot is preserved by the `v0.10.0-pilot-archive` Git tag and
[archived experiment package](thesis/releases/v0.10.0-pilot-artifacts.zip).
See [CHANGELOG.md](CHANGELOG.md) and
[architecture.md](thesis/engineering/architecture.md).
