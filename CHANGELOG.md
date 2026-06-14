# Changelog

All notable changes to this thesis artifact are tracked here.

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
