# External Validation Protocol v1.2.1

## Registration status

This protocol governs the external validation of the thesis:

**Runtime Auditing of Context Bloat in LLM-Based Agents: Detection,
Measurement, and Mitigation Evaluation**

It has two externally timestamped gates. The initial OSF registration must be
completed before any real calibration request. A calibration addendum,
containing the frozen codebook and detector settings, must be registered before
any held-out Study B or Study C request. Study A was not preregistered and must
not be described as preregistered.

## Research questions

- **RQ1:** How accurately can provenance-aware heuristic signals detect and
  localize independently annotated context bloat in natural LLM-agent traces?
- **RQ2:** To what extent do automated context-bloat measures agree with
  independent human judgements and counterfactual removability?
- **RQ3:** What bloat sources and patterns are observed across retrieval,
  memory, and tool workflows under controlled and naturalistic conditions?
- **RQ4:** What token and cost savings, and what task-performance trade-offs,
  arise from provenance-aware mitigation compared with prompt compression?

## Evidence terminology

The study keeps four evidence types separate:

1. **Injected perturbation** is a pattern deliberately introduced in Study A.
2. **Heuristic indicator** is an automated detector output.
3. **Human reference label** is an independent blinded judgement of a context
   segment.
4. **Counterfactually removable** describes a selected segment whose deletion
   preserves adjudicated task success under the frozen replay rule.

Human labels and counterfactual outcomes are distinct validity evidence. They
are not merged into one ground truth. Natural-validation code rejects
`bloat_labels`, injected labels, and detector metadata in request messages.

## Study A: controlled consistency

The existing 1,188 completed task runs and 1,596 invocation traces remain
immutable. The result `F1=1.000` is reported only as controlled pipeline
consistency under fixture-derived labels. It is not evidence of real-world
detection validity. The 360 `combined_bloat` and `mitigated` outputs are
independently scored by two human reviewers, followed by adjudication and an
automatic-scorer confusion matrix.

The fixed Study A conclusion is:

> Token reduction is established for the controlled fixtures, but
> non-inferiority is not established, and the observed evidence is consistent
> with performance degradation.

This sentence does not predetermine the Study C conclusion.

## Provider request contract

Each model call uses a `ModelRequestEnvelope` and records a redacted
client-side serialized request. DeepSeek is configured with
`temperature=0.0`, `max_output_tokens=256`, `thinking=disabled`, and
`max_retries=0`. Because the selected DeepSeek API does not publicly guarantee
seed support, `provider_seed` is null. Repeated calls are called independent
provider replicates under fixed decoding parameters, not deterministic seeded
repetitions.

Every actual dispatch is reserved in the append-only call ledger before network
I/O. Success, timeout, 429, 5xx, other failure, and any manual retry consume one
call. SDK and transport automatic retries are disabled.

The per-cell cap refers to provider invocations, not tool executions. A
retrieval or memory cell may issue at most one provider request. A tool
workflow cell may issue at most two provider requests; any further loop is
terminated before dispatch and recorded as a task failure.

The framework-side capture hash and final client-side serialized payload hash
are recorded. A mismatch raises `payload_mismatch`. The thesis claims
client-side serialized request auditing only; it does not claim visibility
into provider-side transformations.

## Call budget

| Phase | Frozen calculation | Maximum requests |
|---|---:|---:|
| Calibration | 4 tasks per workflow, two frameworks | 32 |
| Study B | 20 retrieval, 20 memory, 20 tool, two frameworks | 160 |
| Study C counterfactual | 18 contexts, 3 variants, 2 replicates | 108 |
| Study C mitigation | 30 tasks, 2 frameworks, 3 arms | 180 |
| Manual retry reserve | eligible timeout, 429, or 5xx only | 20 |
| **Total** | | **500** |

Primary requests cannot exceed 480. The 501st reservation is refused before
dispatch. Manual retries follow original failed-ledger order, each failed
provider invocation is retried at most once, and retry results enter only the
completed-run sensitivity analysis. The intention-to-treat analysis retains
the first request as a failure.

## Resumable execution

Before resume, the runner verifies protocol, config, dataset split, source
bundle, annotation, and dependency hashes. Completed cells are skipped
read-only. Existing traces are never overwritten, and the same run directory
and call ledger are reused. A reserved request is treated as attempted even
when its outcome event is missing, preventing an ambiguous request from being
sent twice.

For a tool cell, only the frozen second envelope may be resumed after a failed
second request; the first request is not repeated. Any hash mismatch refuses
resume and requires a new run.

## Study B: independently annotated natural traces

### Data and execution

The external dataset contains 12 calibration tasks and 60 held-out tasks:

- 20 HotpotQA distractor-development retrieval tasks;
- 20 LongMemEval cleaned memory tasks;
- 20 BFCL multi-turn or multi-step tool tasks.

Calibration contains four tasks per workflow. Source version, selected IDs,
download time, licence notes, sampling seed, and SHA-256 hashes are stored in
the dataset manifest. The same 60 held-out task IDs are attempted through
LangChain and Custom ReAct, giving 120 task-framework cells and up to 120
successfully captured final contexts. No synthetic bloat is injected.

### Human annotation

Two human annotators independently label every eligible segment as `keep`,
`remove`, or `uncertain`, with reason and confidence. Review packages expose
task text, message order, role, and segment text, but hide framework, source
label, condition, detector result, model answer, and automatic score.

Segment IDs and boundaries are frozen before export. Cross-framework segments
are not aligned after annotation. Each reviewer receives independently
randomized blocks of ten contexts. A session contains at most two blocks and
is followed by a break of at least ten minutes. Block start and completion
times are recorded. Agreement is calculated before discussion using percent
agreement, Cohen's kappa, Gwet's AC1, and multiclass Krippendorff's alpha.
Original annotations are immutable; adjudication is stored separately.
Unresolved disagreements remain `uncertain`.

The primary analysis excludes uncertain segments. Sensitivity analysis A
treats uncertain as keep/non-bloat. Sensitivity analysis B treats uncertain as
remove/bloat.

## Study C: counterfactual and mitigation evaluation

### Counterfactual selection

Candidates come only from adjudicated `REMOVE` segments. An eligible candidate
must be non-empty, automatically constructed, non-protected, and have an
adjudicated `KEEP` comparator from the same provenance source. Within each
workflow-framework stratum, at most three contexts are selected with the
frozen randomization seed. The REMOVE candidate is seed-selected. The KEEP
comparator minimizes absolute token-length difference; content hash and segment
ID resolve ties.

If fewer than 18 contexts are eligible, the observed number is reported.
Candidates are not fabricated and selection rules are not changed. Results are
conditional counterfactual evidence for selected human candidates, not a
population-wide removability estimate.

Each context has `original`, `remove_candidate`, and
`remove_matched_keep_control` variants. Each variant receives two independent
provider replicates. A candidate is called counterfactually removable only
when both original replicates succeed and both candidate-removal replicates
retain adjudicated task success.

### Mitigation replay

Thirty task IDs are frozen in advance, ten per workflow, without detector- or
annotation-based selection. Both frameworks contribute one captured final
envelope per task. The three arms are `unmodified`, `provenance_aware`, and
`llmlingua2_budget_matched`.

Each task-framework-arm is a single provider request from the captured final
client-side context. Retrieval, memory, and tool loops are not rerun.
`tool_choice=none`; an unexpected tool call is a task failure. System
instructions, user instructions, tool definitions, and response schema are
protected.

LLMLingua-2 is frozen as:

- `llmlingua==0.2.2`
- `transformers==4.56.2`
- `tokenizers==0.22.1`
- `torch==2.9.0`
- CPU, float32
- model revision `ebaba9b0e874dadd3003ffcff828e4397e568089`

Its budget is matched against canonical serialized managed content retained by
the provenance-aware arm. The allowed difference is
`max(2 tokens, 2 percent)`. All 60 contexts must pass local budget and
protected-content preflight before the first mitigation request.

All successfully generated Study C outputs, up to 288, are independently
scored by both human reviewers in condition-blind blocks of 24. Human
adjudicated task success is primary; automatic scoring is secondary.

## Frozen analysis

The independent unit is the 60 unique `task_id` values. Framework, arm, and
replicate are within-task observations. Every bootstrap resamples complete
task clusters and retains both frameworks and all associated segments.

### RQ1

A human-positive context contains at least one eligible adjudicated `REMOVE`
segment. A detector-positive context contains at least one detector-positive
eligible segment. Standard TP, FP, FN, and TN follow these two binary
definitions. A context with no eligible segment after primary uncertain
exclusion is omitted from the primary analysis.

RQ1 reports context sensitivity, specificity, precision, and F1; task-macro
segment precision, recall, and F1; token-weighted localization IoU; 95 percent
task-cluster bootstrap intervals; and false-positive rate among tasks with no
human-positive context.

### RQ2

Human-reference bloat ratio is adjudicated REMOVE tokens divided by all
eligible annotated tokens. It is compared with the detector-estimated ratio
using Spearman correlation, mean absolute error, calibration slope, and
Bland-Altman bias. Counterfactual validity separately reports selected REMOVE
removability and utility damage after matched KEEP deletion. The former
`MBR=max(RR,NRR,DBR)` self-validation path is excluded.

### RQ3

The sole primary ranking statistic is:

`adjudicated REMOVE tokens for a source / all eligible annotated tokens for that source`

The two frameworks are first combined within task, followed by aggregation
across task IDs. Missing sources are NA and sample counts are reported. Sources
are ordered by point estimate. If the task-cluster bootstrap confidence
interval for a paired source difference includes zero, the sources are
reported as "indistinguishable at the prespecified confidence level", not as
statistically tied or equivalent.

Study A injected-source ranking and Study B human-reference ranking are
compared only by order and Kendall's tau-b, never by absolute ratio. Because
source and workflow are partially confounded, no independent causal source
effect is claimed.

### RQ4

Human-adjudicated task success is primary. Results include managed and provider
prompt tokens, cost, latency, risk difference, 95 percent task-cluster
confidence intervals, and task-clustered GEE. Non-inferiority sensitivity uses
`-2`, `-5`, and `-10` percentage-point margins. The `-5` point margin means at
most one additional failure in twenty tasks. No Study C conclusion is written
before evidence freeze.

Provider failures remain failures in intention-to-treat analysis. A separate
completed-run sensitivity analysis may include the single allowed manual
retry. Study A repetition-level McNemar analysis remains exploratory.

## Deviations and release

No trace is excluded because its result is unfavorable. Source changes,
protocol deviations, scoring corrections, annotation exclusions, and retries
are entered in a dated immutable deviation log before re-analysis.

The execution sequence is:

1. Pass unit, integration, and complete mock E2E tests without held-out real
   provider calls.
2. Publish GitHub Release `v1.2.1-protocol-freeze`.
3. Register the initial OSF protocol and enable calibration only.
4. Run calibration and let two human annotators refine the codebook.
5. Register the calibration addendum containing codebook and detector hashes.
6. Run Study B, freeze independent annotations, calculate agreement, and
   adjudicate.
7. Generate Study C candidates with frozen rules and run Study C.
8. Freeze evidence and publish `v1.2.1-external-validation`.

The final manifest records OSF URLs, Git commit, protocol/config/data/dependency
hashes, model name, and model-call dates.
