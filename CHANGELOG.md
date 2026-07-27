# Changelog

All notable changes to this thesis artifact are tracked here.

## 1.2.1 - Unreleased

- Separated controlled injected labels, heuristic detections, independent
  human-reference annotations, and counterfactual outcomes.
- Added a versioned model-request envelope with separate randomization,
  replicate, and nullable provider seed fields, plus a redacted provider
  request record with canonical payload hashes.
- Added model-visible provenance segments for tool definitions, system
  instructions, and response formats.
- Added a 12-task calibration and 60-task held-out external dataset sampled
  from pinned HotpotQA, LongMemEval, and BFCL v4 sources.
- Added deterministic redaction of credentials and direct identifiers before
  third-party task text is persisted or exported for annotation.
- Added natural Custom ReAct and LangChain execution paths with a shared,
  append-only 500-call ledger, two-phase OSF gates, provider-invocation caps,
  ordered single-use retries, and hash-checked resumable execution.
- Added fully overlapping, condition-blind context and mitigation-outcome
  annotation workbooks with independent block order, session timing, agreement,
  adjudication, and fatigue-trend reports.
- Added counterfactual single-segment removal and a budget-matched
  pinned LLMLingua-2 comparison using one-request final-context replay.
- Replaced circular controlled-label measurement validation with independent
  human-reference and counterfactual evidence builders, task-cluster
  resampling, uncertain-label sensitivity analyses, and a frozen RQ3 ranking
  statistic.
- Added a complete mock Study B/C E2E path without treating mock annotations as
  human evidence.
- Retained schemas 1.1.0 and 1.2.0 as read-only archive inputs.

## 1.1.0 - 2026-07-26

- Added the 36-task context-bloat benchmark with frozen calibration/test splits.
- Added full DeepSeek execution paths for Custom ReAct and actual LangChain
  `BaseChatModel.invoke()` workflows.
- Added versioned ground-truth labels, detected labels, scoring details,
  generation parameters, and primary/stress analysis cohorts to trace schema
  1.1.0.
- Added deterministic detection, localization, measurement, mitigation, and RQ
  evidence reports.
- Added 10,000-sample task-cluster bootstrap intervals and paired McNemar
  diagnostics.
- Added validated study-bundle export with component and analysis Git commits,
  checksums, tables, figures, and immutable trace data.
- Added deterministic condition-blind human-review exports for 72 primary and
  36 second-reviewer outputs.
- Added a clean-worktree gate for paid formal runs.
- Completed and documented the 1596-trace DeepSeek formal study.

## 1.0.0 - 2026-07-26

- Rebuilt the package using a `src/` layout and domain, application, ports,
  adapters, analytics, experiments, and CLI layers.
- Separated production code, tests, configuration, versioned datasets, thesis
  text, source materials, generated runs, and release artifacts.
- Added immutable named run directories with collision protection.
- Added run manifests with config, dataset, environment, output, and SHA-256
  provenance.
- Added `redacted`, `hash-only`, and explicit `full` trace privacy modes.
- Added provider usage and latency models and a strict DeepSeek adapter.
- Replaced the LangChain-compatible fallback with a strict real
  `langchain-core` adapter.
- Added source-aware mitigation decisions and versioned experiment schemas.
- Reorganized tests into unit, integration, and end-to-end layers.
- Archived the v0.10 pilot code under the `v0.10.0-pilot-archive` tag and its
  generated outputs under `thesis/releases/`.

## 0.10.0 - 2026-06-14

- Added DeepSeek provider support through the OpenAI-compatible chat
  completions API.
- Added `check-provider` to report provider environment variable status without
  printing secret values.
- Added `run-real-model-smoke` and `configs/deepseek_smoke.json` for a small
  optional real-model connectivity experiment.
- Hid provider API keys from dataclass repr output.

## 0.9.0 - 2026-06-14

- Added a suite-level `manifest.json` that records artifact version, schema
  version, config paths, output paths, trace counts, and framework comparison
  row counts.
- Updated `run-suite` to print the manifest path after a successful run.
- Documented the manifest as the reproducibility index for thesis experiment
  artifacts.

## 0.8.0 - 2026-06-14

- Added a full experiment suite runner that executes custom ReAct and
  LangChain-compatible pilots from one command.
- Added cross-framework comparison JSON and CSV outputs for configuration-level
  token, redundancy, and task-success comparison.
- Added suite-level mitigation reports for both custom ReAct and
  LangChain-compatible runs.
- Added `run-suite` to the CLI as the recommended reproducibility command.
- Made the custom pilot loop configuration-driven so subset experiment configs
  can be used for fast tests and pilot studies.

## 0.7.0 - 2026-06-14

- Added a LangChain-compatible pilot runner that exercises the callback
  instrumentation boundary while remaining runnable without optional
  dependencies.
- Added `configs/langchain_pilot.json` so custom ReAct and LangChain-compatible
  traces can be generated from aligned experiment matrices.
- Added a `run-langchain-pilot` CLI command.
- Updated tests and documentation for cross-framework pilot experiments.

## 0.6.0 - 2026-06-14

- Externalized the controlled pilot tasks, policy documents, and memory items
  into versioned JSON dataset files.
- Added a dataset loading layer so pilot runs use reproducible experiment
  material instead of hard-coded task constants.
- Added a minimal chat provider abstraction with deterministic mock and
  OpenAI-compatible provider implementations.
- Updated documentation and schema metadata for the v0.6.0 experiment artifact.

## 0.5.0 - 2026-06-13

- Added pre-call message-level mitigation for controlled rerun conditions.
- Added mitigated pilot configurations for retrieval, memory, and tool bloat.
- Added automatic before/after configuration-pair comparison in summaries.
- Updated the custom agent so retrieval and memory answers depend on the
  actually mitigated model-visible context.

## 0.4.0 - 2026-06-13

- Added deterministic local retrieval for semi-real RAG experiments.
- Added retrieval bloat configuration for irrelevant retrieved context.
- Added near-duplicate metrics based on token-set Jaccard similarity.
- Added irrelevant retrieval/memory filtering based on query overlap.
- Added before/after mitigation evaluation over final task invocations.
- Added CSV mitigation reports for thesis RQ4 analysis.

## 0.3.0 - 2026-06-13

- Added trace schema versioning and experiment metadata fields.
- Added configuration-driven pilot experiments through `configs/pilot.json`.
- Added task success and task output fields for performance evaluation.
- Added passage/item-level segmentation for retrieval and memory context.
- Added CSV tables and SVG chart generation for thesis results.
- Added GitHub Actions CI for automated tests.

## 0.2.0 - 2026-06-13

- Reframed the project around context bloat detection, measurement, and mitigation.
- Added package metadata, CLI entry point, semantic versioning, and Git ignore rules.
- Added redundancy and unique-information metrics.
- Added JSONL loading/writing helpers and trace summary analysis.
- Added mitigation utilities for exact duplicate segment removal.
- Expanded tests and documentation for a reproducible thesis workflow.

## 0.1.0 - 2026-06-05

- Initial runtime auditing prototype.
- Added provenance labels, runtime trace capture, pilot custom ReAct agent, and thesis planning documents.
