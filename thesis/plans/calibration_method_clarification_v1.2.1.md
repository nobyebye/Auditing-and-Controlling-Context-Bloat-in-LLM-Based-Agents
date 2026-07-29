# Calibration-Method Clarification v1.2.1

## Status and Scope

This document is a prospective clarification issued after the initial OSF
registration and before the first calibration provider request. It freezes the
deterministic calibration-only threshold-selection procedure and the
fail-closed implementation used to enforce the registered evidence sequence.
It contains no calibration traces, annotations, selected thresholds, or
held-out results.

This prospective clarification specifies a deterministic calibration-only threshold-selection procedure. It does not modify the initial registered datasets, held-out split, outcomes, evidence hierarchy, or primary Study B/C analyses.

The initial registration is:

- OSF URL: https://osf.io/ue4vw/overview
- Registered at: 2026-07-29T12:58:00+03:00

## Calibration Inputs

`calibrate-detector` accepts only:

1. a calibration-only context bundle;
2. the two frozen original human annotation files;
3. the frozen adjudication file; and
4. `annotation_linkage.csv`, which links opaque segment keys to trace and
   segment identifiers.

The calibrator rejects held-out traces and inputs containing task answers,
model outputs, task-success labels, automatic scores, scoring records,
detector predictions, or detected labels. The linkage file contains no task
answer, model output, task-success value, automatic score, or detected label.

## Threshold Definitions

The exact-duplicate signal uses normalized-hash equality and is not searched.
Source dominance is fixed at `source_ratio >= 0.65` and is not searched.
Stale or conflicting context remains a human-reference reason used for error
analysis and has no automatic detector in v1.2.1.

The searched signals are:

| Signal | Positive rule | Candidate grid | More conservative |
|---|---|---|---|
| Near duplicate | `similarity >= threshold` | 0.60 to 0.95 in steps of 0.05 | higher |
| Low query relevance | `relevance <= threshold` | 0, 0.025, 0.05, 0.075, 0.10, 0.15, 0.20 | lower |
| Verbose tool output | `token_count >= threshold` | 40, 60, 80, 100, 120, 160 | higher |

The defaults are 0.80, 0.05, and 80 tokens, respectively.

## Selection Procedure

Each signal is evaluated only against adjudicated `REMOVE` segments carrying
the corresponding human reason. `UNCERTAIN` segments are excluded from the
primary calibration analysis. Segments from both execution paths are combined
within the same real `task_id`, and the objective is task-macro F1.

Candidates are selected in the following deterministic order:

1. higher task-macro F1;
2. higher task-macro precision;
3. smaller distance from the registered default;
4. the more conservative threshold in the direction specified above; and
5. ascending numeric order as the final deterministic decision.

If the corresponding human-positive class is absent, a metric is not
estimable, or annotation coverage is incomplete, the registered default is
retained. The command exports every candidate score, the selected value, the
selection or fallback reason, all input hashes, and
`selected_thresholds.json`.

## Annotation Export Gate

`export-context-annotations` requires an explicit
`--include-split calibration` or `--include-split test`. A bundle containing a
different or mixed split is rejected. Calibration export requires a valid
initial-registration plus clarification evidence chain. Test export remains
blocked until the calibration addendum is registered.

## Evidence-Chain Gate

The local gate derives authorization by verifying the complete evidence chain.
It does not trust a manually editable `*_calls_allowed` flag. For every
required registration it verifies:

- an OSF registration URL and registration timestamp;
- the local package SHA-256 and every package member SHA-256;
- the GitHub release tag and the commit to which it resolves;
- that the release commit contains the identical registered package;
- the preceding registration URL; and
- the current runtime files against the latest registered package.

Calibration requires valid initial-registration and clarification evidence.
Held-out execution requires valid initial-registration, clarification, and
calibration-addendum evidence.

## Study C Intention-to-Treat Rule

Every dispatched Study C provider request remains in the execution table.
Provider errors, timeouts, missing traces, empty outputs, parse failures,
unexpected tool calls, and tool-call violations are coded as task failures in
the primary intention-to-treat analysis. Human reviewers score only outputs
that exist and can be blinded. Human decisions are left-joined to the complete
ledger; absence of a rateable output never removes a dispatched request.

## Outputs After Calibration

After calibration and independent human adjudication, a separate public
calibration addendum will archive `selected_thresholds.json`, the final
codebook, the calibration summary, dataset-split hash, configuration and
dependency hashes, implementation hash, threshold hash, and GitHub release
commit. It will contain no held-out trace or held-out result.
