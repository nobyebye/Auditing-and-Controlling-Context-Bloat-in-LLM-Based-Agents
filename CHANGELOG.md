# Changelog

All notable changes to this thesis artifact are tracked here.

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
