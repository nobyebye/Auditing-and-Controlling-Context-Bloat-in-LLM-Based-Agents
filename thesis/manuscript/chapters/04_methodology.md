# Chapter 4: Research Methodology

## 4.1 Experimental Design

The empirical design contains three studies with different evidential roles.
Study A is the existing controlled perturbation benchmark. Study B validates
the heuristic detector against independently annotated natural traces. Study C
tests counterfactual removability and compares mitigation strategies. Results
from one study are not promoted to a stronger evidence category merely because
they are numerically favorable.

### Study A: controlled perturbation benchmark

Study A uses `context_bloat_benchmark/v1`, containing six calibration tasks and
30 held-out tasks divided equally among retrieval QA, memory-based interaction,
and multi-step tool use. Each held-out task is run under `baseline`,
`sufficient`, `exact_bloat`, `source_specific_bloat`, `combined_bloat`, and
`mitigated` conditions in both frameworks and three repetitions. A separate
six-task cross-source stress cohort uses three conditions.

The accepted Study A artifact contains 1,188 completed task runs and 1,596
model invocations. The injected labels are derived from the same controlled
construction rules that create duplicate, low-relevance, stale, and verbose
segments. Study A therefore verifies trace capture, provenance propagation,
metric calculation, and report consistency. It does not independently validate
detection accuracy.

### Study B: independently annotated natural traces

Study B uses `external_validation/v1`, a frozen 72-task research view with 12
calibration and 60 held-out tasks. Each workflow contributes four calibration
and twenty test tasks. Retrieval tasks are sampled from the HotpotQA distractor
development set [@yang2018hotpotqa]. Memory tasks are sampled from the cleaned
LongMemEval-S release [@wu2025longmemeval]. Tool tasks are a documented
two-turn adaptation of BFCL v4 [@patil2025bfcl]. The adaptation keeps the first
two user turns and corresponding function calls, retains required function
definitions, and adds at most eight deterministic distractor definitions.
Consequently, it is a BFCL-derived call-planning condition, not a reproduction
of the full stateful BFCL evaluator.

Sampling uses seed `20260727`. The dataset manifest records all selected IDs,
source-file hashes, upstream version or repository commit, acquisition time,
licence, and the BFCL transformation. The 12 calibration tasks may be used to
clarify the annotation codebook and choose heuristic thresholds. The 60 test
tasks may not be used for tuning.

Both LangChain and Custom ReAct execute the same 60 held-out tasks, yielding
120 final contexts. Retrieval and memory use one model invocation. Tool tasks
use a planning call and, when a tool call is returned, one final call containing
the generated trace and deterministic tool observations. Study B therefore
requires at most 160 provider calls. No duplicate, relevance, stale-memory, or
verbosity label is embedded in task messages. The external runner rejects any
message containing Study A bloat metadata.

Two human annotators independently label every eligible segment in all 120
final contexts.
They see the task, ordered role, and text, but not task ID, framework,
provenance source, detector output, model answer, or automatic score. Each
segment receives `keep`, `remove`, or `uncertain`, one or more reason codes, and
a confidence value. Reasons are exact duplicate, near duplicate, low query
relevance, stale or conflicting context, verbose tool output, and other.
Agreement is calculated before discussion; disagreements are then adjudicated
without replacing the two original files. The primary analysis excludes
`uncertain`; sensitivity analysis A treats it as `keep/non-bloat`, and
sensitivity analysis B treats it as `remove/bloat`.

### Study C: counterfactual and mitigation evaluation

The counterfactual component selects at most three eligible contexts from every
workflow-framework combination, for no more than 18 contexts. Candidates come
only from adjudicated `REMOVE` segments that are non-empty, automatically
constructed, non-protected, and paired with an adjudicated `KEEP` segment from
the same source. Each context contributes an original request, a request with
the selected `REMOVE` segment deleted, and a request with the closest-length
`KEEP` segment deleted. All variants receive two independent provider
replicates under fixed decoding parameters, giving at most 108 calls. The
selected segment is counterfactually removable only if both original
replicates and both candidate-removal replicates receive adjudicated successful
outcomes. If fewer than 18 contexts qualify, the observed count is reported
without changing the selection rule.

The mitigation component preselects ten task IDs per workflow without using
detector or annotation results. Both frameworks are replayed under
`unmodified`, `provenance_aware`, and `llmlingua2_budget_matched`, giving 180
calls. Every arm is a single controlled completion from the same captured final
context; retrieval, memory, and tool loops are not rerun. LLMLingua-2 is an
extractive, task-agnostic compression baseline [@pan2024llmlingua2]. It receives
the same canonical serialized managed-content token budget retained by the
provenance-aware arm, with tolerance `max(2 tokens, 2%)`. System and user
instructions, response contracts, and tool definitions are protected. Two
human annotators score all 288 Study C outputs while condition and automatic
score remain hidden.

Calibration, Study B, and Study C share a persistent, process-locked ledger
capped at 500 provider invocations. Their primary maxima are 32, 160, and 288,
respectively, leaving 20 calls reserved for ordered manual retries of timeout,
429, or 5xx failures. Every dispatch is reserved before network I/O; failures
and retries consume the ledger. The 501st reservation fails before dispatch.
The initial request remains a failure under intention-to-treat analysis;
successful manual retries enter only a completed-run sensitivity analysis.

Figure 4.1 summarizes the three-study design.

[[FIGURE:experimental_workflow]]

## 4.2 Agent Implementations and Execution Environment

The two execution paths use the same domain models, dataset repository,
tokenizer, detector, provider port, storage adapter, and report builder. The
LangChain path invokes an actual `BaseChatModel`, binds the available tool
schemas, and captures the framework message batch. The Custom ReAct path
constructs the same class of request directly. This comparison demonstrates
that both controlled integration paths can use one auditing core. Because the
context constructors and provider adapter remain shared, it is not treated as
proof of universal framework independence.

Before transport, each path creates a `ModelRequestEnvelope`. The DeepSeek
adapter serializes this envelope into an OpenAI-compatible request body. The
framework capture and serialized payload receive independent canonical hashes.
The actual bytes supplied to the HTTP request are hashed again in the
`ProviderRequestRecord`; a mismatch becomes a trace risk flag. The study can
therefore claim observation of the client-side serialized request, but not
provider-internal transformations.

Study A uses `deepseek-v4-flash`, temperature 0.0, a maximum output length of
256 tokens, and the archived schema-1.1 configurations. Study B and Study C use
the same provider condition with schema 1.2.1, temperature 0.0, a 256-token
output limit, disabled thinking, a 90-second timeout, and no automatic retry.
DeepSeek does not expose a documented reproducible seed for this model, so
`provider_seed` is null and repeated calls are described as independent
provider replicates. Disabling retries makes the call ledger and
intention-to-treat denominator unambiguous. The exact
model identifier, provider, call date, generation parameters, dependency
versions, configuration hash, dataset hash, and Git commit are retained in
each run manifest.

Every run receives a unique non-overwriting directory and begins in `running`
state. Completion records output-file SHA-256 values, token usage, estimated
cost, and status. Resume first verifies protocol, config, dataset, bundle,
annotation, and dependency hashes; completed cells are skipped without
overwriting traces. A reservation without an outcome is conservatively treated
as attempted. Real calibration requires an initial OSF registration. Held-out
Study B/C calls additionally require a calibration addendum containing the
frozen codebook and detector settings. Study A predates this procedure and is
described as frozen, not preregistered.

Persisted requests use redacted mode. Full text is permitted only as an
explicit private condition, while hash-only traces cannot be used for textual
annotation or replay. Public artifacts must not contain full traces, provider
credentials, authorization headers, or raw source downloads.

## 4.3 Evaluation and Statistical Analysis

The independent analysis unit is the 60 held-out `task_id` values. Framework,
intervention, invocation, and repetition are within-task observations.
Confidence intervals use 10,000 deterministic hierarchical bootstrap samples:
task IDs are sampled with replacement, and all observations belonging to each
sampled task remain together. This applies the bootstrap principle
[@efron1979bootstrap] at the actual independence level rather than treating
frameworks or replicates as new tasks.

For RQ1, a human-positive context contains at least one eligible adjudicated
`REMOVE` segment, while a detector-positive context contains at least one
detector-positive eligible segment. Contexts with no eligible segment after
primary uncertain exclusion are omitted. RQ1 reports context sensitivity,
specificity, precision, and F1; task-macro segment precision, recall, and F1;
token-weighted localization IoU; task-cluster 95% confidence intervals; and the
false-positive rate among tasks with no human-positive context. Study A remains
separate injected-rule consistency evidence.

For RQ2, the Human Bloat Ratio is the token share of adjudicated `remove`
segments in a final request. It is compared with the detected token share using
Spearman correlation, mean absolute error, calibration intercept and slope,
and Bland-Altman mean bias and limits of agreement
[@bland1986agreement]. The former composite
measure `max(RR, NRR, DBR)` is excluded because it contains detector output and
cannot independently validate the detector. Counterfactual removability is
reported as a separate behavioral result rather than folded into the same
ratio.

RQ3 reports controlled injected ratios and natural human-reference ratios in
separate tables. Its sole primary ranking statistic is adjudicated REMOVE
tokens for a source divided by all eligible annotated tokens for that source.
The two frameworks are combined within task before aggregation across task
IDs. Missing sources are NA. A paired source-difference interval containing
zero is described as "indistinguishable at the prespecified confidence level",
not as equivalence. Study A and Study B rankings are compared only with
Kendall's tau-b [@kendall1945ties], and source/workflow confounding prevents a causal
interpretation.

RQ4 pairs each mitigation arm with the unmodified request within task and
framework. Outcomes are context-token reduction, provider-reported cost,
latency, deterministic score, and adjudicated human task success. The primary
task-success statistic is the risk difference

$$
\Delta p = p_{\text{intervention}} - p_{\text{unmodified}}.
$$

Non-inferiority is established at the main margin only if the lower 95%
confidence bound is at least -0.05. Sensitivity analyses repeat the decision at
-0.02 and -0.10. These margins are reported as sensitivity evidence rather
than proof of equivalence [@piaggio2012noninferiority]. A task-clustered
logistic GEE [@liang1986gee] is reported as a validation
analysis; if the contrast is non-estimable, that fact is retained rather than
converted to a finite value. Study A's repetition-level McNemar result remains
exploratory.

HotpotQA outputs use the benchmark-style normalized token F1 with a frozen 0.8
success threshold. LongMemEval uses a deterministic contains score as a
reproducible secondary measure because its semantic answers can exceed the
scope of exact matching. BFCL-derived tasks use canonical function name and
argument matching, including positional-to-schema argument conversion. Human
task-success labels are primary for the mitigation comparison precisely
because all three automatic procedures can reject semantically valid outputs
or accept misleading ones.

## 4.4 Human Evaluation, Ethics, and Validity

Context annotation uses 100% overlap by two human reviewers. Before
adjudication, the study reports percent agreement, Cohen's kappa
[@cohen1960coefficient], Gwet's AC1 [@gwet2008variance], and nominal
Krippendorff's alpha. Outcome annotation uses the same overlap and agreement
procedure. Study B workbooks contain ten contexts; Study C workbooks contain 24
outputs; Study A workbooks contain 30 outputs. Each session is limited to two
blocks followed by at least a ten-minute break. Block timestamps support a
fatigue trend check. Original reviewer files, answer keys, adjudication
decisions, input hashes, and agreement reports are retained as distinct
artifacts.

The main construct-validity risk is that context bloat is not directly
observable. A human `remove` judgement may still be wrong, and removability can
depend on a particular model sample. The evidence hierarchy addresses this
without claiming to eliminate it: injected patterns validate software,
independent annotations validate perceived avoidability, and counterfactual
deletion tests utility under two independent provider replicates.

Internal validity benefits from frozen IDs, shared configurations, payload
hashes, task-cluster analysis, and intention-to-treat handling. Remaining risks
include provider-side model changes, lexical retrieval, deterministic mock
tool observations, and possible annotation discussion effects. Deviations are
recorded before analysis is rerun.

External validity remains bounded by one provider condition, sixty held-out
tasks, English-language benchmarks, two controlled execution paths, and a
two-turn BFCL adaptation. HotpotQA, LongMemEval, and BFCL improve realism over
synthetic fixtures but do not represent every deployed retriever, memory
system, or external API. Findings are therefore scoped to observed traces.

For conclusion validity, three repetitions in Study A and two counterfactual
replicates do not create new independent tasks. All uncertainty calculations retain
`task_id` as the cluster. The -5 percentage-point margin is interpreted as at
most one additional failure per twenty tasks rather than presented as a
domain-independent standard. Information-preservation research similarly
shows why compression ratio must be evaluated with downstream utility and
retained content [@lajewska2025information].
