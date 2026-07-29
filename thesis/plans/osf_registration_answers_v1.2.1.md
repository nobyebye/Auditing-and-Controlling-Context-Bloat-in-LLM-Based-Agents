# OSF Registration Answers - v1.2.1 External Validation

This document maps every answer to the corresponding OSF registration
question. Text under **Paste this answer** can be copied directly into OSF.

The implementation/package alignment checks at the end of this document have
been completed. Use the corrected R1 archive and identifiers recorded below.

## Metadata

### Title

**Paste this answer**

```text
Runtime Auditing of Context Bloat in LLM-Based Agents: Detection, Measurement, and Mitigation Evaluation
```

### Description

**Paste this answer**

```text
This registration archives the v1.2.1 external-validation protocol for a study of context bloat in LLM-based agents. The study evaluates a provenance-aware runtime-auditing approach across three evidence layers: controlled pipeline consistency (Study A), natural agent traces with independent human annotation (Study B), and conditional counterfactual removal and mitigation comparisons (Study C).

The protocol freezes the request ledger, provider-invocation budget, datasets, annotation procedure, statistical analysis plan, and protected-context rules before any v1.2.1 calibration or Study B/C provider request is dispatched. Study B and Study C had not started at the time of registration. After the public registration and its timestamp are verified, the local protocol gate permits calibration only. Held-out evaluation remains blocked until a post-calibration OSF addendum records the already-frozen dataset-split hash and freezes the calibrated detection thresholds, final annotation codebook, and dependency hashes.
```

### Contributors

**Enter**

```text
Guochen Li
```

### License

**Select**

```text
MIT License
```

**Year**

```text
2026
```

**Copyright Holders**

```text
Guochen Li
```

The MIT license covers the original software and documentation deposited with
the registration. Third-party benchmark materials remain subject to their
upstream licenses and are not relicensed by this selection.

### Subjects

**Select**

```text
Engineering
Artificial Intelligence and Robotics
Physical Sciences and Mathematics
Computer Sciences
```

### Tags

**Enter**

```text
context bloat
LLM-based agents
preregistration
prompt compression
provenance-aware
runtime auditing
```

## Overview

### Research Questions or Hypotheses

**Paste this answer**

```text
Prospective scope: This registration prospectively covers the v1.2.1 calibration phase and Studies B and C. Study A was completed before registration and is treated only as fixed prior controlled evidence.

RQ1: How accurately can provenance-aware heuristic signals detect and localize independently annotated context-bloat candidates in natural LLM-agent contexts?

RQ2: To what extent do automated context-bloat measures agree with adjudicated human judgments and, separately, with conditional counterfactual removability among selected REMOVE candidates?

RQ3: What source-level human-reference bloat-token ratios and predefined annotation-reason patterns are observed across retrieval, memory, and tool workflows, and how do their rankings compare with the fixed injected-source ranking previously observed in Study A?

RQ4: Relative to unmodified context and budget-matched LLMLingua-2 compression, what token, cost, and latency savings, and what task-success risk differences, arise from provenance-aware mitigation?
```

### Foreknowledge of Data or Evidence

**Select this option**

```text
Analyses in this plan have been conducted already. At least some of the analyses described in this analysis plan have been conducted by the authors making this a retrospective registration.
```

This conservative option is required because Study A was already completed and
analyzed. The following explanation separates that retrospective evidence from
the prospective calibration and Studies B/C.

### Explanation of Foreknowledge and Managing Unintended Influences

**Paste this answer**

```text
This is a mixed-status registration. Study A, the controlled perturbation study, was completed and analyzed before this registration. Its results informed the design of the external-validation protocol and are treated as fixed prior evidence rather than prospectively registered findings.

The prospective scope of this registration is the v1.2.1 calibration phase and Studies B and C. At the time of submission, no v1.2.1 calibration request, Study B or Study C provider request, independent human annotation, adjudication, counterfactual replay, mitigation comparison, or confirmatory Study B/C analysis had been conducted.

The benchmark datasets existed before registration, and the authors accessed sufficient dataset structure and task information to construct and freeze task identifiers, workflow strata, calibration and held-out splits, execution code, and annotation materials. The authors had also observed the completed Study A results.

To limit unintended influence, the protocol freezes the task splits, provider-invocation ledger and budget, analysis unit, annotation codebook, uncertain-label sensitivity analyses, candidate-selection rules, outcome measures, clustered resampling procedure, and mitigation comparison before calibration begins. Calibration tasks are excluded from confirmatory analyses. Held-out execution remains blocked until a public post-calibration OSF addendum records the already-frozen dataset-split hash and freezes the calibrated detection thresholds, final annotation codebook, and dependency hashes.
```

## Research Design

### Study Type

**Select all three**

```text
Non-randomized study
Descriptive study
Simulation study
```

Do not select Randomized Experiment, Quasi-experimental Study, Systematic
Review or Meta-analysis, or Other.

### Intention for Causal Interpretation

**Select**

```text
No causal relationship inferred
```

### Blinding of Experimental Treatments

**Select only**

```text
Researchers or observers who code or interpret data for analysis will not be aware of the assigned treatments during coding.
```

### Additional Blinding During Research or Analysis

**Paste this answer**

```text
Study B annotators will receive task instructions, message order, message roles, and segment text, but will not see the framework identity, provenance source labels, detector outputs, experimental condition, model answer, automatic score, or the other annotator's decisions. The two annotators will complete their raw annotations independently. Agreement statistics will be calculated and the original annotations frozen before adjudication begins.

For Study C, task-success assessors will be blinded to whether an output was produced by the unmodified, provenance-aware, or LLMLingua-2 arm. Output identifiers and presentation order will be independently randomized using a frozen seed. For the retrospective Study A review, assessors will similarly be blinded to the combined-bloat and mitigated condition labels.

The analysts cannot remain blinded after the annotations and experimental metadata are merged for statistical analysis. To limit analyst discretion, the eligibility rules, outcome definitions, task-level clustering, uncertainty analyses, and statistical procedures are frozen before held-out execution.
```

### Study Design

**Paste this answer**

```text
This investigation is a mixed, non-randomized, repeated-measures software-systems evaluation with three evidence layers.

Study A is included only as fixed retrospective evidence. Its archived traces and original statistical results will not be modified. The newly collected retrospective human-review outcomes will be stored and reported as a separate evidence block.

Study B prospectively evaluates natural agent traces using 60 held-out tasks: 20 retrieval tasks, 20 memory tasks, and 20 tool-use tasks. Every task is attempted through both LangChain and Custom ReAct, giving 120 task-framework cells and up to 120 successfully captured final contexts. No duplicate, irrelevant, stale, verbose, or detector-derived labels are injected. Retrieval and memory cells may issue at most one provider request; tool cells may issue at most two provider requests.

Two human annotators independently label every eligible Study B segment as KEEP, REMOVE, or UNCERTAIN. The primary analysis excludes UNCERTAIN labels; sensitivity analyses treat them first as KEEP and then as REMOVE. Raw annotations are frozen before adjudication.

Study C contains two paired evaluations. The counterfactual evaluation selects up to 18 contexts using prespecified workflow-framework strata. Each selected context is evaluated using the original context, removal of one adjudicated REMOVE segment, and removal of a token-matched adjudicated KEEP segment. Each variant receives two independent provider replicates, giving a maximum of 108 requests.

The mitigation evaluation uses 30 prespecified tasks, with 10 tasks per workflow. Each task-framework context is replayed once under three arms: unmodified context, provenance-aware mitigation, and budget-matched LLMLingua-2 compression. This schedules 180 final-context replay requests and can produce up to 180 outputs. Retrieval, memory, and tool loops are not re-executed during replay.

Workflow family is a between-task factor. Framework, context variant, and mitigation arm are within-task repeated factors. The independent analysis unit is task_id. Confidence intervals use task-clustered bootstrap resampling, and task-clustered GEE is used as a validation analysis. Failed provider requests remain failures in the intention-to-treat analysis.

The complete calibration, Study B, Study C, and retry budget is capped at 500 actual provider requests. Each dispatch, including failed requests and manual retries, is charged to the append-only call ledger before transmission.
```

### Study Design File Upload

After the corrected protocol package has been regenerated, attach:

```text
external_validation_protocol_v1.2.1.md
annotation_codebook_v1.2.1.md
osf_external_validation_protocol_v1.2.1-r1.zip
```

Do not upload raw provider traces, API credentials, `.env` files, incomplete
human annotations, or third-party raw benchmark datasets.

### Randomization

**Paste this answer**

```text
This is not a randomized experiment, and tasks are not randomly assigned to experimental conditions. Each eligible task receives all applicable framework or mitigation conditions in a paired repeated-measures design.

Frozen pseudo-random seeds are used only for prespecified sampling and presentation procedures: selecting up to three eligible counterfactual contexts per workflow-framework stratum, selecting among eligible REMOVE candidates, ordering annotation blocks, counterbalancing output presentation, and statistical bootstrap resampling. Hash-based tie-breaking is used where specified.

Provider replicates are independent requests under fixed decoding parameters. Because the provider does not document deterministic seed support, these requests are not described as reproducible randomized-seed trials.
```

## Sampling

### Data Collection Procedures

**Paste this answer**

```text
The primary sampled units are benchmark task records and generated agent contexts. Two adult human assessors will provide annotation and task-success judgments. The study does not investigate or draw inferences about the assessors' personal characteristics. Reviewer identities will be pseudonymized; only reviewer identifiers and annotation-block timing required for reliability and fatigue diagnostics will be retained.

The sampling frame contains three pinned public sources representing three workflow families: the HotpotQA distractor development set v1 for retrieval, the LongMemEval cleaned release for memory, and BFCL v4 multi-turn tasks for tool use. Source versions, acquisition dates, licenses, source hashes, selected record identifiers, and the derived-task hash are archived in the accompanying dataset manifest.

A frozen base seed of 20260727 and source-specific deterministic offsets are used to select 24 unique tasks from each source: four calibration tasks and twenty held-out tasks. HotpotQA records are sorted by source identifier before seeded sampling. LongMemEval records are grouped by question type and sampled using a seeded round-robin procedure to preserve question-type diversity. BFCL records are eligible only when the derived workflow contains no more than two conversation turns; eligible records are sorted before seeded sampling. The resulting dataset contains 72 unique tasks. Calibration and held-out task identifiers are fixed and cannot be exchanged after registration.

The 60 held-out tasks comprise 20 retrieval, 20 memory, and 20 tool-use tasks. Every held-out task is attempted through both LangChain and Custom ReAct, giving 120 task-framework cells and up to 120 successfully captured final contexts. Retrieval and memory cells may issue at most one provider request, while a tool cell may issue at most two provider requests. The per-cell cap refers to provider invocations, not tool executions. If a tool workflow still requests another model or tool step after the second provider invocation, the loop is terminated before a third request is dispatched. No synthetic bloat labels, injected perturbations, or detector metadata are included in Study B messages.

Every successfully captured final Study B context is segmented using boundaries frozen before annotation. Two human annotators independently label each eligible automatically constructed segment as KEEP, REMOVE, or UNCERTAIN, with a reason and confidence value. Annotation packages hide framework identity, provenance source labels, detector outputs, experimental condition, model answer, automatic score, and the other annotator's decisions. Raw annotations are frozen before agreement analysis and adjudication.

Study C counterfactual candidates are selected only from adjudicated REMOVE segments that are non-empty, automatically constructed, non-protected, and have a same-source adjudicated KEEP comparator. At most three contexts are selected from each workflow-framework stratum. The mitigation sample consists of 30 task identifiers fixed before annotation, with ten per workflow; it is not selected using detector outputs or human labels.

Data collection is expected to take approximately eight weeks after initial registration. Calendar duration does not change the sample size or stopping rules. All persisted task and trace text is processed under redacted privacy mode.
```

### Data Collection Procedures - File Upload

Leave empty. The three protocol files are attached once under Study Design and
do not need to be uploaded repeatedly.

### Sample Size

**Paste this answer**

```text
The calibration sample contains 12 unique tasks: four retrieval, four memory, and four tool-use tasks. These tasks are executed through two frameworks but are excluded from confirmatory Study B/C analyses.

The primary Study B analysis contains 60 independent task_id clusters: 20 HotpotQA retrieval tasks, 20 LongMemEval memory tasks, and 20 BFCL tool-use tasks. Each task is attempted through LangChain and Custom ReAct, giving 120 task-framework cells and up to 120 successfully captured final contexts. Framework observations and all segments belonging to the same task remain nested within that task. Segment counts may differ naturally between contexts.

Study C counterfactual evaluation includes at most 18 framework-task contexts: up to three from each of the six workflow-framework strata. Each context has three variants: original, removal of an adjudicated REMOVE candidate, and removal of a token-matched adjudicated KEEP control. Each variant receives two independent provider replicates. The maximum is therefore 108 counterfactual requests and up to 108 outputs. If fewer than 18 contexts meet the frozen eligibility criteria, the smaller observed sample is reported without replacement.

Study C mitigation evaluation contains 30 prespecified task IDs, ten per workflow. Each task contributes two framework contexts and three paired replay arms: unmodified, provenance-aware mitigation, and budget-matched LLMLingua-2. This schedules 180 mitigation requests and can produce up to 180 outputs.

Both human annotators assess all eligible segments in every successfully captured Study B context, all successfully generated Study C outputs up to a maximum of 288, and 360 frozen Study A outputs. The provider-request ceiling is 32 calibration requests, 160 Study B requests, 108 counterfactual requests, 180 mitigation requests, and 20 reserved manual retries, for an absolute maximum of 500 requests.
```

### Sample Size Rationale

**Paste this answer**

```text
The sample size is a prespecified feasibility and coverage decision rather than the result of a conventional power calculation. Reliable effect-size estimates for independently annotated context bloat and clustered task-success contrasts are not available for prospective power estimation.

Twenty held-out tasks per workflow provide balanced representation of retrieval, memory, and tool-use contexts while keeping complete double annotation feasible. Running every held-out task through both frameworks creates paired within-task comparisons without treating framework executions as independent tasks. The 30-task mitigation subset preserves ten tasks per workflow and applies all three arms to both frameworks. The counterfactual cap of three contexts per workflow-framework stratum provides balanced conditional evidence while limiting the number of repeated provider evaluations.

Two provider replicates are required for counterfactual removability so that a candidate is not declared removable after a single favorable response. The study emphasizes effect estimates, task-clustered confidence intervals, uncertainty analyses, and transparent sample counts rather than post hoc expansion until statistical significance. The sample will not be increased or replaced based on observed results.
```

### Starting and Stopping Rules

**Paste this answer**

```text
Real calibration begins only after the initial OSF registration is public, its immutable registration URL, timestamp, and file hashes have been verified, and the local calibration gate has been enabled. Calibration ends after all 12 calibration tasks have been attempted through both frameworks subject to the per-cell invocation caps, or when the 32-request calibration ceiling is reached. Calibration tasks are never included in held-out analyses.

After calibration, two human annotators may clarify the codebook using calibration materials only. A public post-calibration OSF addendum must record the already-frozen dataset-split hash and freeze the calibrated detection thresholds, final annotation codebook, and dependency hashes. No held-out Study B or Study C provider request may be dispatched before that addendum is verified.

Study B ends after every frozen held-out task-framework cell has been attempted or the applicable request ceiling is reached. Tasks are not replaced because of provider failure, unfavorable output, missing human-positive segments, or detector error. Study C begins only after Study B raw annotations, agreement statistics, and adjudication are frozen.

Counterfactual collection stops after all eligible prespecified strata have been processed, up to 18 contexts. If fewer contexts qualify, the observed number is retained. All 60 mitigation framework-task contexts must pass local protected-content and token-budget preflight before the first mitigation request is sent.

The append-only ledger reserves every provider request before dispatch. Primary requests cannot exceed 480, and no more than 20 additional requests are available for eligible timeout, HTTP 429, or HTTP 5xx failures. Automatic retries are disabled; each eligible failed invocation may be retried once in original ledger order. The 501st request is refused before transmission.

Execution is paused on a payload-hash mismatch, privacy violation, protocol/config/data/dependency hash mismatch, or corrupted annotation state. Completed cells are not overwritten or resent. Data collection is not stopped early because of statistical significance, apparent performance, token reduction, or an unfavorable result.

Before a run is resumed, the protocol, configuration, dataset split, source bundle, annotation, and dependency hashes are verified. Completed cells are skipped read-only, the same run directory and append-only ledger are reused, and no completed provider request is sent again. If the second provider request of a tool cell fails, only that frozen second-request envelope may be retried; the first provider request and tool execution are not repeated. A hash mismatch requires a new run rather than an in-place resume.
```

## Variables

### Manipulated Variables

**Paste this answer**

```text
None. This is not a randomized experiment. Workflow family, framework, counterfactual variant, and mitigation arm are prespecified comparison factors in a paired repeated-measures software evaluation, not randomly assigned treatments.
```

### Manipulated Variables - File Upload

Leave empty.

### Measured Variables

**Paste this answer**

```text
Grouping and design variables include task_id, source dataset, dataset split, workflow family (retrieval, memory, or tool use), framework (LangChain or Custom ReAct), invocation index, evidence tier, counterfactual variant, mitigation arm, provenance source type, and provider replicate identifier. The task_id is the independent clustering unit.

Segment-level measurements include message role, provenance source type, character count, token count, exact content hash, normalized content hash, protected-content status, annotation eligibility, detector-positive status, detector reason, and detected pattern type. Human annotation variables include independent KEEP, REMOVE, or UNCERTAIN decisions, reason category, confidence, reviewer identifier, block index, block start and completion times, and the final adjudicated decision. Original reviewer decisions are retained separately from adjudication.

Context- and invocation-level measurements include total characters, total context tokens, tokens by provenance source, exact-duplicate and near-duplicate segment counts and token counts, provider input and output tokens, latency, estimated or provider-reported cost, request status, error category, payload-mismatch status, and framework/provider payload hashes.

The primary Study B reference variables are adjudicated human segment decisions. Automated detector outputs are treated as heuristic indicators and are not treated as ground truth. Study A injected labels remain a separate retrospective evidence type.

Task-outcome variables include the model output, automatic task score, automatic binary task success, and condition-blind human-adjudicated binary task success. Human-adjudicated task success is primary for Study C; automatic scoring is secondary. Provider timeout, HTTP 429, HTTP 5xx, unexpected tool call, invocation-cap termination, and other API failures are recorded and treated as task failures in the intention-to-treat analysis.

Variables used for predefined subsetting are calibration versus held-out split, workflow family, framework, provenance source, evidence tier, experimental arm, annotation eligibility, and uncertain-label policy. A context with no eligible annotated segment after primary exclusion of UNCERTAIN segments is excluded from the primary RQ1/RQ2 context analysis, and the excluded count is reported. No trace is excluded because of an unfavorable detector or task-performance result.
```

### Measured Variables - File Upload

Leave empty.

### Indices

**Paste this answer**

```text
Let t(s) denote the token count of segment s and T(c) = sum_s t(s) denote the total tokens in context c.

Source Contribution Ratio for source q:
SCR(q,c) = sum_{s: source(s)=q} t(s) / T(c).

Exact Redundancy Ratio:
RR(c) = tokens in repeated normalized-hash segments after their first occurrence / T(c).

Near-Redundancy Ratio:
NRR(c) = tokens in same-source segments whose token-set Jaccard similarity with an earlier segment meets the threshold frozen in the post-calibration addendum / T(c). The held-out data will not be used to select this threshold.

Unique Information Ratio:
UIR(c) = 1 - RR(c).

Context Growth Rate between consecutive invocations:
CGR_i = (T_i - T_{i-1}) / T_{i-1}. It is undefined when the preceding context has zero tokens.

For an annotated context, eligible tokens are tokens in segments retained under the applicable UNCERTAIN policy. The primary policy excludes UNCERTAIN segments. Sensitivity analysis A treats UNCERTAIN as KEEP; sensitivity analysis B treats UNCERTAIN as REMOVE.

Human-Reference Bloat Token Ratio:
HBR(c) = adjudicated REMOVE tokens / all eligible annotated tokens.

Detector-Estimated Bloat Token Ratio:
DBR(c) = detector-positive eligible tokens / all eligible annotated tokens.

A human-positive context contains at least one eligible adjudicated REMOVE segment. A detector-positive context contains at least one detector-positive eligible segment. Context-level sensitivity, specificity, precision, and F1 use the resulting TP, TN, FP, and FN counts. Segment precision = TP/(TP+FP), recall = TP/(TP+FN), and F1 is their harmonic mean. Segment metrics are first calculated after combining both framework contexts within task_id and then macro-averaged across defined task values.

Token-Weighted Localization IoU:
IoU(c) = tokens in the intersection of detector-positive and adjudicated-REMOVE segment sets / tokens in their union. Context values are averaged within task_id and then across tasks.

Human-measure agreement is summarized by Spearman correlation between HBR and DBR, mean absolute error mean(|HBR-DBR|), linear calibration intercept and slope with HBR as outcome and DBR as predictor, and Bland-Altman bias mean(DBR-HBR).

The sole primary RQ3 source-ranking statistic is:
total adjudicated REMOVE tokens for a source / total eligible annotated tokens for that source.
Both frameworks are first combined within task_id; source totals are then aggregated across task clusters. A missing source is recorded as NA.

A counterfactual candidate is removable only when both original provider replicates have adjudicated task success and both candidate-removal replicates preserve success. Candidate preservation rate is the number of complete contexts satisfying this rule divided by the number of complete counterfactual contexts. Matched-KEEP degradation rate is the proportion of complete baseline-successful contexts in which at least one KEEP-removal replicate fails.

For mitigation arm a relative to the unmodified arm:
Token reduction = T(unmodified) - T(a).
Token reduction ratio = [T(unmodified) - T(a)] / T(unmodified).
Human task-success difference = Success(a) - Success(unmodified).
Cost and latency reductions are defined analogously as unmodified minus arm values.

Framework-level paired differences are averaged within task_id before aggregation across tasks. Confidence intervals resample complete task_id clusters. Non-inferiority at margin m is established only when the lower bound of the 95% task-cluster confidence interval for the human success difference is at least m, reported separately for m = -0.02, -0.05, and -0.10.

Human-review reliability is reported using raw percent agreement, Cohen's kappa, Gwet's AC1, and multiclass Krippendorff's alpha before adjudication. Human labels and counterfactual outcomes are reported as separate validity evidence and are never combined into a single ground-truth index.
```

### Indices - File Upload

Leave empty.

## Analysis Plan

### Statistical Models

**Paste this answer**

```text
The independent analysis unit is task_id. Both framework executions, all invocations, all segments, and all repeated arms belonging to a task remain within the same task cluster. Primary 95% confidence intervals use 10,000 percentile bootstrap samples with seed 20260726. Each bootstrap draw resamples complete task_id clusters with replacement and retains both frameworks and all associated observations.

Inter-annotator agreement is calculated before adjudication using percent agreement, Cohen's kappa, Gwet's AC1, and nominal multiclass Krippendorff's alpha. Disagreements are adjudicated only after the original annotations and agreement results are frozen.

RQ1 uses human-adjudicated segment labels as the reference and detector outputs as predictions. At context level, a context is human-positive when it contains at least one eligible adjudicated REMOVE segment and detector-positive when it contains at least one detector-positive eligible segment. Context sensitivity, specificity, precision, and F1 are calculated from TP, TN, FP, and FN counts. Segment precision, recall, and F1 are calculated after combining both framework contexts within task_id and are then macro-averaged across tasks for which the relevant denominator is defined. Token-weighted localization IoU and the false-positive rate in human-negative contexts are also reported. All primary RQ1 metrics receive task-cluster bootstrap intervals. No regression model or universal accuracy threshold is used to convert these estimates into a general claim of detector validity.

RQ2 compares the human-reference bloat token ratio with the detector-estimated ratio. The analyses are Spearman rank correlation, mean absolute error, an ordinary least-squares calibration equation HBR = beta_0 + beta_1 DBR + error, and Bland-Altman mean bias with limits of agreement equal to mean bias plus or minus 1.96 standard deviations. Spearman correlation receives a task-cluster bootstrap interval. Human-reference agreement and counterfactual removability are treated as separate validity evidence and are not combined into one ground-truth variable.

RQ3 is descriptive and does not estimate a causal source effect. Both frameworks are first combined within task_id. For each provenance source, the primary statistic is total adjudicated REMOVE tokens divided by total eligible annotated tokens. Sources are ranked by this point estimate. Source estimates and pairwise source-ratio differences receive task-cluster bootstrap intervals. If a pairwise interval contains zero, the sources are described as indistinguishable at the prespecified confidence level, not equivalent or statistically tied. The Study A injected-source ranking and Study B human-reference ranking are compared using Kendall's tau-b only; absolute ratios are not compared.

RQ4 counterfactual analysis reports the candidate-preservation rate and matched-KEEP degradation rate among complete, prespecified candidate sets. The original context is the baseline, and deletion of a token-matched adjudicated KEEP segment is the control for nonspecific deletion harm.

For mitigation, provenance-aware and LLMLingua-2 arms are separately compared with the unmodified arm. Token, human-success, automatic-success, cost, and latency differences are calculated within each framework-task pair, averaged across frameworks within task_id, and then averaged across tasks. Token-reduction and task-success differences receive task-level bootstrap intervals.

As a secondary validation model, each mitigation arm versus unmodified is fitted using a separate binomial logistic generalized estimating equation with an intercept and one binary arm indicator (unmodified = 0; comparison arm = 1), task_id as the clustering variable, an independence working correlation, and robust standard errors. Framework is retained as a repeated observation within task but is not entered as a causal covariate. A GEE result is reported only when its coefficient, standard error, p-value, and confidence interval are finite; otherwise it is reported as not estimable without replacing the primary bootstrap analysis.

Manipulation checks require all 60 mitigation contexts to preserve protected content and pass LLMLingua-2 token-budget matching within max(2 tokens, 2%) before any mitigation request. A payload mismatch, protected-content violation, or failed preflight stops execution rather than triggering an alternative analysis.
```

### Statistical Models - File Upload

Leave empty.

### Transformations

**Paste this answer**

```text
No continuous variable will be centered, standardized, winsorized, log-transformed, or otherwise transformed unless explicitly defined as a ratio in the registered indices.

Annotation decisions are coded REMOVE = 1 and KEEP = 0. Under the primary policy, UNCERTAIN is excluded. Sensitivity analysis A codes UNCERTAIN as KEEP/0, and sensitivity analysis B codes UNCERTAIN as REMOVE/1.

Human and automatic task success are coded success = 1 and failure = 0. Provider failures remain failure/0 in the intention-to-treat analysis. For each secondary GEE comparison, unmodified is coded 0 and the relevant mitigation arm is coded 1.

Workflow family, framework, source type, split, evidence tier, counterfactual variant, and mitigation arm retain their registered categorical labels. They are used for grouping, stratification, or descriptive subgroup analysis rather than ordinal coding. Missing provenance sources are represented as NA, not zero.

Token and character counts remain non-negative integer counts; provider cost remains USD; latency remains milliseconds. Ratio variables remain on the [0,1] scale. Framework observations are averaged within task only for the prespecified paired Study C contrasts.
```

### Inference Criteria

**Paste this answer**

```text
The analysis is estimation-focused. Effect estimates, 95% confidence intervals, denominators, task counts, and applicability limits are primary. RQ1 and RQ2 do not use a fixed threshold for declaring the detector universally supported or unsupported.

All bootstrap intervals are two-sided 95% percentile intervals based on 10,000 resamples of complete task_id clusters using seed 20260726. The primary uncertain-label policy excludes UNCERTAIN; the two extreme recodings are reported as sensitivity analyses.

For RQ3, a pairwise source-difference interval containing zero is interpreted as indistinguishable at the prespecified confidence level. It is not interpreted as proof of equivalence. Source ranking is descriptive because provenance source and workflow are partially confounded.

For RQ4, human-adjudicated task success is primary and automatic scoring is secondary. Non-inferiority is evaluated using the lower bound of the two-sided 95% task-cluster confidence interval for Success(arm) - Success(unmodified). The primary margin is -0.05, interpreted as a utility tolerance corresponding to no more than one additional failure per twenty comparable task executions. Sensitivity margins are -0.02 and -0.10. Non-inferiority at margin m is established only when the lower confidence bound is at least m.

GEE p-values are two-sided and reported with alpha = 0.05 as secondary validation evidence. They do not override the task-cluster bootstrap estimates. No omnibus ANOVA and no unregistered follow-up significance tests are planned.

No multiplicity-adjusted confirmatory p-value family is defined because RQ1-RQ3 are estimation/descriptive analyses and the GEE tests are secondary. All prespecified metrics, source comparisons, mitigation contrasts, and sensitivity margins will be reported; no result will be selected according to statistical favorability.
```

### Data Inclusion and Exclusion

**Paste this answer**

```text
All 12 frozen calibration tasks and all 60 frozen held-out task IDs will be attempted. Calibration observations are excluded from confirmatory Study B/C results. Task IDs are not replaced because of provider failure, unfavorable output, detector error, missing bloat, or annotation disagreement.

Study B RQ1-RQ3 include final natural-evidence contexts that were actually captured and independently annotated. Protected system instructions, user instructions, tool definitions, response schemas, empty segments, and segments outside the automatically constructed context are not annotation-eligible. Segment IDs and boundaries are frozen before annotation and are not aligned across frameworks after observation.

Under the primary policy, UNCERTAIN segments are excluded. If no eligible segment remains in a context, that context is excluded from the corresponding primary context analysis and the excluded count is reported. The context is retained under applicable sensitivity policies.

No token, cost, latency, ratio, or task-success outlier is removed, trimmed, or winsorized. Extreme values remain in the analysis and may be described separately without changing the primary estimates.

Study C counterfactual candidates must be adjudicated REMOVE, non-empty, automatically constructed, non-protected, and accompanied by a same-source adjudicated KEEP comparator. If fewer than 18 contexts qualify, the smaller sample is reported without replacement.

Study C mitigation uses only the 30 task IDs frozen before annotation and includes all three arms for both frameworks. Provider failures, invocation-cap termination, and unexpected tool calls are task failures in the intention-to-treat analysis. Retry outcomes appear only in the completed-run sensitivity analysis.

A trace with payload mismatch is treated as a failed cell and explicitly reported. Hash mismatch, privacy violation, or corrupted annotation state pauses execution; affected data are not silently repaired, overwritten, or excluded.
```

### Missing Data

**Paste this answer**

```text
No statistical imputation is planned.

A provider request that fails, times out, returns HTTP 429 or 5xx, exceeds the invocation cap, or returns an unexpected tool call is coded as task failure in the intention-to-treat analysis. A single permitted manual retry does not replace the original failure and is used only in the completed-run sensitivity analysis.

When no final context exists, segment-level detection and localization measures cannot be calculated for that cell. The cell remains in execution and failure accounting, while the corresponding context metric is recorded as unavailable. Availability counts and reasons are reported.

Incomplete human annotation prevents the confirmatory analysis from running. Unresolved reviewer disagreements are retained as UNCERTAIN rather than imputed. The primary and two sensitivity policies then handle UNCERTAIN as prespecified.

Undefined precision, recall, specificity, F1, correlation, or calibration quantities caused by a zero denominator or insufficient variation are reported as not estimable. Task-macro summaries use only tasks for which the relevant metric is defined and report the effective task count.

A provenance source absent from a task is NA rather than a zero-ratio observation. Missing provider usage, cost, or latency fields are reported as unavailable for the corresponding secondary metric and are not used to infer zero resource use.
```

### Other Planned Analysis

**Paste this answer**

```text
Secondary analyses include the two UNCERTAIN-label sensitivity policies; completed-run sensitivity using the single permitted retry; automatic-scorer confusion matrices relative to adjudicated human task success; descriptive results by workflow, framework, mitigation arm, and annotation reason; and annotation-fatigue diagnostics using disagreement rate by block and its slope over block order.

Study A automatic scores will be compared with the double-reviewed adjudicated outcomes for all 360 frozen combined-bloat and mitigated outputs. Study A results remain retrospective and are not pooled with Study B human-reference estimates.

The Study A injected-source ranking and Study B human-reference ranking will be compared using Kendall's tau-b. Framework-stratified and workflow-stratified summaries may be reported descriptively, but they will not be interpreted as independent causal effects.

Protocol deviations, API-error patterns, payload mismatches, source availability, and annotation exclusions will be summarized descriptively. Any additional analysis not specified above will be clearly labeled exploratory and will not replace the registered primary analyses.
```

## Other

### Context and Additional Information

**Paste this answer after inserting the final release information**

```text
This is a mixed-status registration. Study A, a controlled perturbation experiment comprising fixed prior evidence, was completed and analyzed before this registration. The prospective scope of this registration comprises the v1.2.1 calibration phase and Studies B and C. No v1.2.1 calibration request, Study B or Study C provider request, independent annotation, adjudication, counterfactual replay, mitigation comparison, or confirmatory Study B/C analysis had been conducted at the time of registration.

The study distinguishes four evidence types: injected perturbations, heuristic indicators, adjudicated human-reference labels, and counterfactual outcomes. Heuristic detector outputs are not treated as ground truth. Human judgments and counterfactual removability are analyzed as separate forms of validity evidence and are not combined into a single reference label.

Two independent human annotators will complete the Study B segment annotations and the Study A/C task-success assessments. No AI system will be represented as an independent human annotator. Agreement will be calculated from the frozen original annotations before discussion-based adjudication. Unresolved disagreements will remain uncertain and will be handled using the prespecified primary and sensitivity analyses.

The runtime-auditing system records the final client-side serialized provider request. It does not claim to observe undocumented transformations performed within the provider's server infrastructure. The shared provenance schema is exercised through two controlled execution paths, LangChain and Custom ReAct; this is not presented as evidence of universal framework independence.

Calibration may begin only after this registration has been made public and its immutable registration URL and timestamp have been recorded in the study manifest. Held-out Study B/C execution remains blocked until a public post-calibration OSF addendum records the already-frozen dataset-split hash and freezes the calibrated detection thresholds, final annotation codebook, and dependency hashes. The initial registration will not be modified to incorporate calibration decisions. Any subsequent protocol deviation will be timestamped, justified, and reported separately from the preregistered analyses.

The corresponding corrected protocol freeze is archived at:
https://github.com/nobyebye/Auditing-and-Controlling-Context-Bloat-in-LLM-Based-Agents/releases/tag/v1.2.1-protocol-freeze-r1

The frozen source commit is 6d2f5025e46f19a4b5a749854b5fafe457776dac. The packaging commit associated with the release tag is 763e46e26d6e87485da17f617e381f2b12a886de. The SHA-256 checksum of the attached protocol archive is d74c6ab6ecbfe135c9757297a8120efd14c5f3c16bfae35cf018c2cd6c2232d0.
```

## Optional Upload Fields

For the repeated optional upload controls under Sampling, Variables, and
Analysis Plan, select no additional files. The same protocol files should not
be uploaded repeatedly.

## Pre-Submission Engineering Checks

The following checks were completed before publishing the corrected R1
package:

1. Missing provider cost and latency remain unavailable and are never coerced
   to zero.
2. The Study A/Study B source-ranking comparison implements Kendall's tau-b.
3. Protocol text uses "up to 120" and "up to 288" where provider failures can
   reduce the number of generated contexts or outputs.
4. The corrected package passes the complete mock E2E and Python test suite.
5. The corrected archive is generated from a clean frozen commit.
6. The new GitHub release URL, source commit, packaging commit, and SHA-256 are
   copied into the OSF answer and registration manifest.
7. The three corrected attachments are visible in the OSF draft.
8. The initial registration remains unsubmitted until the OSF draft has been
   updated with these corrected answers and attachments.
