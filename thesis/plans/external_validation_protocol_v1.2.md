# External Validation Protocol v1.2

## Registration status

This document is a registration-ready protocol. It has not yet been registered
on OSF. The OSF registration URL and timestamp must be added before any paid
test-split call is made. The earlier controlled study was not preregistered and
must not be described as such.

## Research questions

RQ1 asks how accurately provenance-aware heuristic signals detect and localize
independently annotated context bloat in natural agent traces.

RQ2 asks how closely automated bloat measures agree with independent human
judgements and counterfactual removability.

RQ3 asks which source-specific patterns are observed under controlled
perturbations and natural retrieval, memory, and tool workflows.

RQ4 asks which token and cost savings, and which task-performance trade-offs,
arise from provenance-aware mitigation relative to budget-matched prompt
compression.

## Evidence tiers

- Injected perturbation: a pattern deliberately created in Study A.
- Heuristic indicator: an automated detector output.
- Human reference label: a blinded, independently produced segment judgement.
- Counterfactually removable: a segment whose removal preserves task success
  in both frozen repetitions.

These terms are not interchangeable. Injected labels are not accepted by the
Study B or Study C execution paths.

## Study A

The existing schema-1.1 formal study is retained unchanged. Its 1,188 completed
task runs and 1,596 traces test controlled pipeline consistency. Perfect
agreement with labels derived from fixture metadata is not external detection
or measurement validity.

## Study B

The external dataset contains 12 calibration tasks and 60 held-out tasks:
20 HotpotQA retrieval tasks, 20 cleaned LongMemEval memory tasks, and 20 BFCL
multi-turn or multi-step tool tasks. The same 60 test IDs are run through
Custom ReAct and LangChain. Retrieval and memory use one answer call. Tool
workflows use at most two calls.

Task IDs are selected once with seed `20260727`. Source files, versions, record
IDs and SHA-256 values are stored in the dataset manifest. Calibration data may
be used to clarify the codebook and tune detector thresholds. Test labels and
detector outputs remain hidden until the annotation files are frozen.

Both annotators label every segment in all 120 final test contexts. The review
files hide task ID, framework, condition, provenance source, detector result,
model output and automatic score. Agreement is reported before adjudication
using raw agreement, Cohen's kappa, Gwet's AC1 and nominal Krippendorff alpha.

## Study C

Counterfactual evaluation selects three eligible contexts from each
workflow-framework combination. Each context contributes an unmodified request,
a request with one consensus-remove segment removed, and a request with a
token-matched consensus-keep segment removed. The three variants are replayed
with two frozen repetition seeds, giving 108 calls.

Mitigation evaluation selects ten paired tasks per workflow. Both frameworks
are replayed under unmodified, provenance-aware and LLMLingua-2 conditions,
giving 180 calls. LLMLingua-2 receives the managed-source token budget retained
by the provenance-aware method. System instructions, user messages and tool
definitions are protected.

Study B and Study C share a persistent call ledger with a hard limit of 500
HTTP attempts. API failures count as task failures in the intention-to-treat
analysis. Completed-run results are secondary sensitivity evidence.

## Analysis

The independent unit is `task_id`. Framework, intervention and repetition are
within-task observations. Confidence intervals resample task IDs and retain all
observations belonging to each sampled task.

RQ1 reports task-macro binary precision, recall and F1, subtype metrics,
localization accuracy and task-cluster confidence intervals. RQ2 compares the
token-weighted human-reference bloat ratio with the detected ratio using
Spearman correlation, mean absolute error, calibration slope and Bland-Altman
bias. RQ3 reports source distributions and uncertainty without claiming a
universal causal ranking.

RQ4 reports token, cost, latency and task-success risk differences separately.
The `-5` percentage-point non-inferiority margin represents at most one
additional failure per twenty tasks. Sensitivity results use `-2`, `-5` and
`-10` percentage points. Repetition-level McNemar results from Study A are
exploratory only.

## Frozen exclusions and deviations

No completed test trace is removed because of an unfavorable output. Missing
or failed calls remain in the intention-to-treat denominator. Protocol
deviations, source-data changes, scoring corrections and annotation exclusions
must be recorded in a dated deviation log before analysis is rerun.

## Frozen execution sequence

All commands are run from the repository root. Generated paths under `runs/`
are illustrative; the actual immutable run IDs printed by the commands must be
substituted where indicated.

1. Validate the pinned dataset and run the no-cost calibration paths:

```powershell
context-auditor validate-dataset `
  --dataset-name external_validation `
  --dataset-version v1

context-auditor run-external-suite `
  --custom-config configs/experiments/external_calibration_custom_react_v1.2.json `
  --langchain-config configs/experiments/external_calibration_langchain_v1.2.json
```

2. Freeze the upload package. This command records SHA-256 values in the local
   registration manifest and leaves paid calls disabled:

```powershell
context-auditor freeze-external-protocol
```

3. Upload `thesis/releases/osf_external_validation_protocol_v1.2.zip` to an
   immutable OSF registration. After registration, set
   `registration_status` to `registered`, enter the public registration URL and
   timestamp, set `registered_commit`, and explicitly set
   `paid_test_calls_allowed` to `true`. Do not change the frozen hashes.

4. From a clean committed worktree, run Study B:

```powershell
context-auditor run-external-suite --confirm-real-cost
```

The two printed run directories are exported as one bundle:

```powershell
context-auditor export-study `
  --run <custom-react-run-directory> `
  --run <langchain-run-directory> `
  --output runs/studies/external-validation-v1.2.zip

context-auditor validate-study `
  --bundle runs/studies/external-validation-v1.2.zip
```

5. Export two identical, blinded forms. Reviewers work independently and must
   not access `answer_key.csv`:

```powershell
context-auditor export-context-annotations `
  --bundle runs/studies/external-validation-v1.2.zip `
  --output runs/annotations/context-v1.2 `
  --annotation-set-id context-v1.2

context-auditor import-context-annotations `
  --reviewer runs/annotations/context-v1.2/reviewer_a.csv `
  --answer-key runs/annotations/context-v1.2/answer_key.csv `
  --output runs/annotations/context-v1.2-imported-a `
  --annotation-set-id context-v1.2 `
  --reviewer-id reviewer-a

context-auditor import-context-annotations `
  --reviewer runs/annotations/context-v1.2/reviewer_b.csv `
  --answer-key runs/annotations/context-v1.2/answer_key.csv `
  --output runs/annotations/context-v1.2-imported-b `
  --annotation-set-id context-v1.2 `
  --reviewer-id reviewer-b

context-auditor adjudicate-annotations `
  --reviewer-a runs/annotations/context-v1.2-imported-a/annotations.csv `
  --reviewer-b runs/annotations/context-v1.2-imported-b/annotations.csv `
  --answer-key runs/annotations/context-v1.2/answer_key.csv `
  --output runs/adjudication/context-v1.2 `
  --annotation-set-id context-v1.2
```

All `REQUIRES_CONSENSUS` rows in `adjudication.csv` must be resolved before the
evidence builder is run:

```powershell
context-auditor build-external-evidence `
  --bundle runs/studies/external-validation-v1.2.zip `
  --adjudication runs/adjudication/context-v1.2/adjudication.csv `
  --answer-key runs/annotations/context-v1.2/answer_key.csv `
  --output runs/evidence/context-v1.2 `
  --annotation-set-id context-v1.2
```

6. Run Study C using the immutable Study B bundle and resolved context
   adjudication:

```powershell
context-auditor run-counterfactual-suite `
  --bundle runs/studies/external-validation-v1.2.zip `
  --adjudication runs/adjudication/context-v1.2/adjudication.csv `
  --answer-key runs/annotations/context-v1.2/answer_key.csv `
  --annotation-set-id context-v1.2 `
  --confirm-real-cost
```

The command prints a unique Study C run directory. Its
`traces/invocations.jsonl` is then reviewed:

```powershell
context-auditor export-outcome-annotations `
  --traces <study-c-run-directory>/traces/invocations.jsonl `
  --output runs/annotations/outcomes-v1.2 `
  --annotation-set-id outcomes-v1.2

context-auditor adjudicate-outcomes `
  --reviewer-a runs/annotations/outcomes-v1.2/reviewer_a.csv `
  --reviewer-b runs/annotations/outcomes-v1.2/reviewer_b.csv `
  --answer-key runs/annotations/outcomes-v1.2/answer_key.csv `
  --output runs/adjudication/outcomes-v1.2 `
  --annotation-set-id outcomes-v1.2

context-auditor build-study-c-evidence `
  --traces <study-c-run-directory>/traces/invocations.jsonl `
  --outcome-adjudication runs/adjudication/outcomes-v1.2/adjudication.csv `
  --outcome-answer-key runs/annotations/outcomes-v1.2/answer_key.csv `
  --output runs/evidence/study-c-v1.2
```

The Study B and Study C commands share the same persistent call ledger. The
expected maximum is 160 Study B attempts plus 288 Study C attempts, or 448,
leaving 52 attempts for explicitly documented failures while enforcing the
hard limit of 500.
