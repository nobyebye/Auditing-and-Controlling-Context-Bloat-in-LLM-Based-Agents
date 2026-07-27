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

Two annotators independently label every segment in all 120 final contexts.
They see the task, ordered role, and text, but not task ID, framework,
provenance source, detector output, model answer, or automatic score. Each
segment receives `keep`, `remove`, or `uncertain`, one or more reason codes, and
a confidence value. Reasons are exact duplicate, near duplicate, low query
relevance, stale or conflicting context, verbose tool output, and other.
Agreement is calculated before discussion; disagreements are then adjudicated
without replacing the two original files.

### Study C: counterfactual and mitigation evaluation

The counterfactual component selects three eligible contexts from every
workflow-framework combination, for 18 contexts in total. Each contributes an
unmodified request, a request with one consensus `remove` segment deleted, and
a request with a token-matched consensus `keep` segment deleted. All three
variants are executed with seeds `20260727` and `20260728`, giving 108 calls.
A candidate is classified as counterfactually removable only if both deletion
repetitions succeed and neither score is below its paired unmodified baseline.

The mitigation component preselects ten task IDs per workflow. Both frameworks
are replayed under `unmodified`, `provenance_aware`, and
`llmlingua2_budget_matched`, giving 180 calls. LLMLingua-2 is an extractive,
task-agnostic compression baseline [@pan2024llmlingua2]. It receives the same
managed-source token budget retained by the provenance-aware arm. System and
user instructions, response contracts, and tool definitions are protected.
Two annotators score all 180 mitigation outputs while condition and automatic
score remain hidden.

Study B and Study C share a persistent, process-locked ledger capped at 500
HTTP attempts. Their frozen maximum is 448, leaving 52 attempts for failures or
documented recovery. The 501st reservation fails before a provider request can
be created. API failures remain failures under intention-to-treat analysis; a
completed-run analysis is secondary.

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
the same provider condition with schema 1.2.0, temperature 0.0, a 256-token
output limit, a 90-second timeout, and no automatic retry. Disabling retries
makes the call ledger and intention-to-treat denominator unambiguous. The exact
model identifier, provider, call date, generation parameters, dependency
versions, configuration hash, dataset hash, and Git commit are retained in
each run manifest.

Every run receives a unique non-overwriting directory and begins in `running`
state. Completion records output-file SHA-256 values, token usage, estimated
cost, and status. Real Study B/C runs require a clean worktree and an externally
timestamped OSF registration containing the frozen protocol, codebook,
configuration, conclusion rules, schema, and dataset manifest. Study A predates
this procedure and is described as frozen, not preregistered.

Persisted requests use redacted mode. Full text is permitted only as an
explicit private condition, while hash-only traces cannot be used for textual
annotation or replay. Public artifacts must not contain full traces, provider
credentials, authorization headers, or raw source downloads.

## 4.3 Evaluation and Statistical Analysis

The independent analysis unit is the 60 held-out `task_id` values. Framework,
intervention, invocation, and repetition are within-task observations.
Confidence intervals use 10,000 deterministic hierarchical bootstrap samples:
task IDs are sampled with replacement, and all observations belonging to each
sampled task remain together.

RQ1 reports binary segment precision, recall, and F1; task-macro binary F1;
reason-subtype metrics; and segment localization accuracy. Binary localization
requires the correct segment, not the same reason name. Study A results are
reported separately as injected-rule consistency. Study B results use only
adjudicated human `remove` segments as the reference.

For RQ2, the Human Bloat Ratio is the token share of adjudicated `remove`
segments in a final request. It is compared with the detected token share using
Spearman correlation, mean absolute error, calibration intercept and slope,
and Bland-Altman mean bias and limits of agreement. The former composite
measure `max(RR, NRR, DBR)` is excluded because it contains detector output and
cannot independently validate the detector. Counterfactual removability is
reported as a separate behavioral result rather than folded into the same
ratio.

RQ3 reports controlled injected ratios and natural human-reference ratios in
separate tables. Source and workflow means include task-cluster bootstrap
intervals. Pairwise workflow contrasts include mean differences and Hedges'
$g$. A ranking is written as an observation under the sampled tasks and
context-construction policy, not as a general causal ordering.

RQ4 pairs each mitigation arm with the unmodified request within task and
framework. Outcomes are context-token reduction, provider-reported cost,
latency, deterministic score, and adjudicated human task success. The primary
task-success statistic is the risk difference

$$
\Delta p = p_{\text{intervention}} - p_{\text{unmodified}}.
$$

Non-inferiority is established at the main margin only if the lower 95%
confidence bound is at least -0.05. Sensitivity analyses repeat the decision at
-0.02 and -0.10. A task-clustered logistic GEE is reported as a validation
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

Context annotation uses 100% reviewer overlap. Before adjudication, the study
reports percent agreement, Cohen's kappa, Gwet's AC1, and nominal
Krippendorff's alpha. Outcome annotation uses the same overlap and agreement
procedure. Original reviewer files, answer keys, adjudication decisions, input
hashes, and agreement reports are retained as distinct artifacts.

The main construct-validity risk is that context bloat is not directly
observable. A human `remove` judgement may still be wrong, and removability can
depend on a particular model sample. The evidence hierarchy addresses this
without claiming to eliminate it: injected patterns validate software,
independent annotations validate perceived avoidability, and counterfactual
deletion tests utility under two fixed repetitions.

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
seeds do not create new independent tasks. All uncertainty calculations retain
`task_id` as the cluster. The -5 percentage-point margin is interpreted as at
most one additional failure per twenty tasks rather than presented as a
domain-independent standard. Information-preservation research similarly
shows why compression ratio must be evaluated with downstream utility and
retained content [@lajewska2025information].
