# Chapter 5: Empirical Results

This chapter currently reports the frozen Study A evidence and defines the
tables into which Study B results will be inserted. Study B has not yet passed
the external-registration and human-adjudication gates. Consequently, this
draft does not assign a final positive status to RQ1, RQ2, or RQ3.

Study A contains 1,596 model invocations and 1,188 completed task runs. The
primary cohort contributes 1,380 traces and 1,080 final results from 30
held-out tasks; the cross-source stress cohort contributes 216 traces and 108
final results from six reused tasks. The provider reported 218,434 input tokens
and 205,164 output tokens. Estimated API cost was USD 0.0787, and mean
invocation latency was 2,448.8 ms. These are provenance facts for one provider
condition and date, not general cost estimates.

## 5.1 Controlled Detection and Localization Consistency

The Study A primary cohort contains 1,122 injected
`(trace, segment, label)` tuples. Table 5.1 reports their agreement with the
heuristic detector.

| Injected label | Reference tuples | True positives | False positives | False negatives | F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Exact duplicate | 360 | 360 | 0 | 0 | 1.000 |
| Low query relevance | 342 | 342 | 0 | 0 | 1.000 |
| Near duplicate | 240 | 240 | 0 | 0 | 1.000 |
| Verbose tool output | 180 | 180 | 0 | 0 | 1.000 |
| **Total** | **1,122** | **1,122** | **0** | **0** | **1.000 overall** |

Macro-F1 and same-segment localization are both 1.000, with task-cluster
bootstrap intervals [1.000, 1.000]. This result verifies internal consistency:
the context constructor placed the intended perturbation, instrumentation
preserved its provenance, and the matching deterministic rule recovered it.
The label generator and detector share the same source metadata and thresholds.
The result therefore cannot estimate accuracy on independently labelled
context.

The guard also produced 468 `duplicate_segments` flags, 259
`context_growth_spike` flags, 156 tool-dominance flags, and 33
retrieval-dominance flags across both cohorts. These invocation-level signals
are operational diagnostics, not additional reference labels.

Study B will replace the injected reference with the adjudicated decisions of
two annotators. Its main RQ1 table reports binary task-macro precision, recall,
and F1, subtype errors, localization accuracy, 95% task-cluster intervals, and
the number of independently labelled tasks. Until those values are frozen, the
defensible conclusion is:

> The detector is internally consistent with the controlled perturbation
> rules; accuracy and localization in natural traces remain to be established.

## 5.2 Controlled Measurement and Source Patterns

Across the 1,080 final Study A primary invocations, the injected bloat ratio
and detector-derived ratio are identical by construction, and their Spearman
correlation is 1.000. This is not an independent validation of measurement.
The former schema-1.1 analysis included detector output in its measured
composite and compared it with labels derived from matching fixture rules.
Schema 1.2 removes that circular comparison from RQ2.

The controlled condition progression remains useful as a perturbation check.

| Condition | Invocation traces | Mean context tokens | Mean exact redundancy ratio | Mean injected bloat ratio |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 180 | 42.70 | 0.000 | 0.000 |
| Sufficient | 240 | 68.20 | 0.000 | 0.000 |
| Exact bloat | 240 | 76.03 | 0.113 | 0.113 |
| Source-specific bloat | 240 | 150.05 | 0.000 | 0.364 |
| Combined bloat | 240 | 224.73 | 0.178 | 0.437 |
| Mitigated | 240 | 75.87 | 0.000 | 0.096 |

Exact duplication raises lexical redundancy. Source-specific fixtures raise the
injected ratio without raising exact redundancy because they use near
duplicates, low-overlap passages, stale memory, or verbose tool detail.
Combined bloat produces the largest context. The table establishes sensitivity
of the metrics to known changes, not semantic validity.

Table 5.3 reports source attribution under those fixtures.

| Source | Total tokens | Injected tokens | Aggregate injected ratio | Mean source-specific injected ratio |
| --- | ---: | ---: | ---: | ---: |
| Tool | 49,560 | 48,480 | 0.978 | **0.500** |
| Retrieval | 14,394 | 8,424 | 0.585 | **0.487** |
| Memory | 8,118 | 4,818 | 0.593 | **0.468** |

Under the controlled fixture design, tool segments have the highest mean
injected ratio, followed by retrieval and memory. The differences are small,
and the fixture generator deliberately assigns verbose diagnostics to tool
outputs. The result must not be rewritten as "tool output is the main source of
context bloat in real agents."

The natural RQ2 analysis will compare detected and human-reference bloat ratios
using Spearman correlation, mean absolute error, calibration slope, and
Bland-Altman bias. The natural RQ3 table will add source-specific bootstrap
intervals and workflow effect sizes. A source ranking will be stated only as:
"within the sampled natural traces and construction policy."

## 5.3 Framework and Stress-Case Comparison

Study A uses the same fixtures, detector, provider, and scorer in both
execution paths. Each framework contributes 690 primary traces and 540 final
primary results.

| Framework | Primary traces | Mean context tokens | Mean injected bloat ratio | Task success |
| --- | ---: | ---: | ---: | ---: |
| Custom ReAct | 690 | 109.95 | 0.1755 | 73.15% |
| LangChain | 690 | 108.11 | 0.1759 | 72.04% |

The close context values show that both integrations feed the same controlled
construction into a shared auditing core. They do not prove framework
equivalence. Schema 1.2 strengthens the instrumentation test by comparing a
framework-capture hash with the provider payload hash and by counting tool
definitions as model-visible context.

The stress cohort averages 241.12 context tokens, compared with 109.03 in the
primary cohort. Mean exact redundancy is 0.119 versus 0.051, and mean near
redundancy is 0.181 versus 0.078. Stress task success is 84.26%, compared with
72.59% in the primary cohort, but the cohorts are not treatment-equivalent:
stress tasks always receive supporting context, while the primary matrix
contains a no-support baseline.

Stress mitigation reduces tokens by 79.68% on average (95% CI [79.06%,
80.25%]) and changes task success by -16.67 percentage points (95% CI
[-38.89, 0.00]). These values reinforce the need to measure utility alongside
compression.

## 5.4 Status of RQ1-RQ3

Study A establishes that the runtime pipeline can represent source provenance,
recover deliberately injected patterns, attribute tokens, preserve immutable
run metadata, and distinguish primary from stress evidence. It does not
establish external detection or measurement validity.

Final answers to RQ1-RQ3 require all of the following Study B artifacts:

1. Two clean real-provider runs covering the same 60 held-out task IDs.
2. A validated schema-1.2 bundle with no payload mismatches or injected labels.
3. Two complete blind annotation files and pre-adjudication agreement.
4. A resolved consensus label for every segment in all 120 final contexts.
5. Task-cluster statistical output built from the immutable bundle and
   adjudication hashes.

Until those artifacts exist, RQ1 and RQ2 have insufficient independent
evidence, while RQ3 has controlled descriptive evidence only. This temporary
status is stricter than the earlier `Supported` labels and is intentionally
used to prevent internal consistency from being presented as external
validation.
