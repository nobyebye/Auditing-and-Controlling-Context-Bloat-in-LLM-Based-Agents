# Chapter 6: Mitigation Evaluation and Discussion

## 6.1 Mitigation Effectiveness

The controlled mitigation experiment in Study A compared the
`combined_bloat` and `mitigated` final invocations for the same task,
framework, and repetition. The analysis comprised 180 paired outcomes derived
from 30 underlying task IDs. The intervention recorded 438 provenance-linked
decisions and removed 51,042 context tokens before the final model calls.

The mean absolute reduction was 198.48 tokens per pair. The mean
token-reduction ratio was 48.85%, with a task-cluster bootstrap 95% confidence
interval of [42.67%, 55.31%]. This interval establishes that the implemented
rules reduced context size in the controlled fixtures. It does not establish
that the removed content was unnecessary.

The task-success result points in the opposite direction. Success under
mitigation minus success under `combined_bloat` was -6.11 percentage points,
with a 95% confidence interval of [-12.22, -0.56]. Of the 180 repeated pairs,
157 did not change binary outcome, six improved, and 17 degraded. An exploratory
exact McNemar test gave \(p=0.0347\). Because repetitions and frameworks do not
create new independent tasks, this test is not treated as confirmatory
evidence. Nevertheless, both the direction of the clustered interval and the
imbalance of discordant pairs are consistent with a performance-degradation
risk.

The correct conclusion from Study A is therefore asymmetric. Token reduction
is established for the controlled intervention, but task-performance
non-inferiority is not established. The result should not be summarized merely
as `Inconclusive`, because the observed interval excludes zero and is
compatible with harm. Nor does the result prove that every removed segment was
necessary: model variability, evidence placement, and the automatic scorer may
all contribute. It shows that provenance-aware deletion remains an
intervention whose utility must be tested.

Table 6.1 reports descriptive workflow and framework breakdowns. These
subgroups were not independently powered and should be read as diagnostic
patterns.

| Group | Pairs | Mean token reduction | Mean reduction ratio | Task-success difference |
| --- | ---: | ---: | ---: | ---: |
| Retrieval QA | 60 | 40.20 | 32.40% | -3.33 pp |
| Memory turns | 60 | 26.50 | 29.96% | -11.67 pp |
| Multi-step tool | 60 | 528.73 | 84.18% | -3.33 pp |
| Custom ReAct | 90 | 198.98 | 48.71% | -2.22 pp |
| LangChain | 90 | 197.98 | 48.98% | -10.00 pp |

The large reduction in the tool workflow follows directly from the fixture
design: its injected tool observations contain a concise result followed by
repeated diagnostic detail. Memory shows the largest descriptive success loss,
whereas the LangChain path loses more than the Custom ReAct path. These
differences identify cases for inspection, not stable workflow or framework
effects.

The controlled cross-source stress cohort produced a mean reduction of 79.68%
(95% CI [79.06%, 80.25%]) and a task-success difference of -16.67 percentage
points (95% CI [-38.89, 0.00]). Eight repeated pairs degraded and two improved.
This result reinforces the central engineering lesson: a high compression
ratio is not evidence that an intervention preserved the information needed by
the task.

Study C is designed to supply the missing comparative evidence. It replays 30
held-out tasks through both execution paths under three conditions:
unmodified context, provenance-aware mitigation, and LLMLingua-2
[@pan2024llmlingua2]. The compression baseline receives the same retained-token
budget as the provenance-aware method, while system instructions, user
messages, and tool definitions remain protected. The analysis reports token,
cost, latency, automatic task score, and condition-blind human task success.
At the time of this draft, the Study C software and mock validation are
complete, but the registered real-model results have not been collected.
Consequently, no comparative Study C effect is reported here.

## 6.2 Counterfactual Necessity and Interpretation

The definition of context bloat requires more than a detector flag. A segment
may look duplicated, irrelevant, stale, or verbose while still affecting the
answer. The revised evidence model therefore distinguishes four concepts:
injected perturbations, heuristic indicators, human reference annotations, and
counterfactual removability. Only the last concept directly tests whether a
candidate segment can be removed without an observed utility loss under the
specified replay conditions.

The Study C counterfactual suite selects 18 contexts, with three contexts from
each workflow-by-framework combination. Each selected context is paired with
one consensus `remove` segment and one token-length-matched consensus `keep`
segment. The original request, candidate-removal request, and necessary-segment
removal request are each replayed with two fixed seeds, yielding 108 calls. A
candidate is classified as counterfactually removable only when both
candidate-removal repetitions preserve task success relative to the original.
Removing the matched `keep` segment acts as a negative control.

This design does not turn counterfactual removability into a universal fact.
The result remains conditional on the task definition, model, request
serialization, seed pair, and scorer. It is nevertheless more informative than
deriving a label from the same metadata consumed by the detector. Agreement
between human `remove` judgments and successful counterfactual deletion
provides evidence that the annotation captures avoidable content. Disagreement
is equally useful: it identifies cases in which apparent redundancy or
irrelevance carries latent utility.

Study A already illustrates why this distinction matters. Exact and near
duplicates often repeat relevant evidence. Low-overlap retrieval can provide a
bridging fact for multi-hop reasoning. A verbose tool response may contain one
essential field near its end. Repetition can also change the salience or
position of a fact even when it adds no new lexical information. These
mechanisms explain why a rule can correctly match an injected label yet still
decrease task success after removal.

The source ranking from Study A is likewise conditional on the perturbation
process. Tool output had the highest injected-bloat ratio (0.500), followed by
retrieval (0.487) and memory (0.468), but the differences are small and the
fixtures deliberately assigned different bloat mechanisms to the three
workflows. The defensible statement is that tool-output segments had the
highest injected-bloat ratio under these controlled fixtures. Study B will
estimate independently annotated source ratios in natural traces and attach
task-cluster confidence intervals to those estimates.

Prompt-compression research supports the same utility-aware interpretation.
Compression methods are normally evaluated on downstream quality as well as
token reduction, and recent work argues that information preservation must be
measured directly rather than inferred from prompt length
[@lajewska2025information]. The present thesis extends this principle with
source provenance and segment-level intervention records. The purpose is not
to declare one compression family universally superior, but to make the
efficiency-utility trade-off auditable.

## 6.3 Engineering Implications

The first implication concerns the capture boundary. Framework callbacks can
observe messages before a provider adapter serializes them, while application
logs may record only user input and final output. Version 1.2 therefore stores
both a framework-side `ModelRequestEnvelope` and a redacted
`ProviderRequestRecord`. Their canonical hashes reveal whether the two
representations differ. For the DeepSeek adapter, the provider record is
computed from the same serialized bytes passed to the HTTP transport.

This mechanism supports a precise but limited claim: the framework captures the
client-side serialized request. It cannot observe transformations performed
inside the provider service, such as undocumented instruction insertion,
tokenization, caching, or routing. A `payload_mismatch` flag also prevents a
trace with inconsistent capture hashes from silently entering the evidence
set.

The second implication is that token accounting should preserve provenance. An
aggregate token count can identify an expensive call but cannot tell a
developer whether retrieval, memory, tool output, tool schemas, generated
traces, or framework instructions caused the increase. Source contribution and
source-localized indicators connect an observation to a plausible engineering
action.

The third implication is that detection should precede intervention. The
auditor can run in observation mode, collect growth and redundancy indicators,
and expose the relevant segment without modifying behavior. Automatic
mitigation should be enabled only after its candidate selection, protected
segments, token budget, and task-utility effects have been validated for the
target workflow.

The fourth implication is that mitigation decisions require their own audit
trail. A shorter request is not inherently explainable. Each decision records
the affected segment, action, reason, source, and estimated token change.
These records allow a failure to be traced back to a specific deletion or
compression and support policies that protect instructions, tool definitions,
or selected memory records.

The fifth implication concerns experimental reproducibility. Agent studies
combine code, configuration, source datasets, model calls, retries, generated
outputs, annotations, and statistical decisions. Versioned datasets, unique run
directories, manifests, payload hashes, call ledgers, immutable bundles, and
protocol hashes are therefore part of the research method. They constrain
researcher degrees of freedom and make negative results recoverable rather than
disposable.

Finally, the two execution paths demonstrate adapter reuse, not universal
framework independence. LangChain and Custom ReAct share the same dataset,
provider interface, detector, and analysis core. Their successful integration
shows that the schema is not tied to one callback API. It does not show that
all frameworks construct equivalent contexts or that the findings generalize
to multi-agent systems.

## 6.4 Limitations and Future Work

The principal current limitation is evidential. Study A provides internally
consistent controlled data but not independent validation. Study B and Study C
have complete data, execution, annotation, adjudication, and evidence-building
pipelines, and those pipelines have passed mock end-to-end validation. Their
real-model test split remains intentionally blocked until the protocol receives
an external OSF timestamp. The thesis must not replace those pending results
with mock values.

Human annotation introduces a second limitation. Judging whether a segment is
removable can require domain knowledge and counterfactual reasoning. The
protocol therefore uses two independent annotators for every final Study B
context, reports raw agreement, Cohen's kappa, Gwet's AC1, and Krippendorff's
alpha before adjudication, and retains both original label files. Even with
this procedure, a consensus label is a reference judgment rather than absolute
ground truth.

The natural-trace datasets are broader than the controlled fixtures but remain
bounded. HotpotQA supplies retrieval questions, LongMemEval supplies memory
sessions, and a documented two-turn adaptation of BFCL supplies tool-use
requests [@yang2018hotpotqa; @wu2025longmemeval; @patil2025bfcl]. The local
retriever, memory selection policy, and deterministic tool implementations do
not reproduce every production RAG, long-term memory, or external API system.

The detector remains primarily lexical and rule-based. Exact hashes do not
capture semantic repetition; token overlap can misclassify paraphrases;
relevance depends on multi-hop reasoning; and a length threshold cannot
determine whether a structured tool field is useful. Future detectors could
combine embeddings, entailment, temporal memory metadata, structured schemas,
and calibrated uncertainty while retaining segment-level explanations.

The provider scope is also limited. The validation protocol fixes one provider
and one served model version. Provider-side updates may occur even when the
client model name remains stable. Model call date, configuration, serialized
payload hash, and dependency versions are recorded, but they cannot make a
hosted model fully reproducible.

The independent unit is the set of 60 Study B task IDs. Framework, condition,
and repetition are within-task measurements rather than additional independent
samples. Hierarchical bootstrap intervals and task-clustered GEE respect this
structure, but workflow-specific effects will still be imprecise. A larger
multi-provider study would be required for strong interaction claims.

Future work should extend the counterfactual design to combinations of
segments, longer agent trajectories, multilingual prompts, and adaptive
context budgets. More capable mitigation could preserve structured tool fields,
summarize with explicit coverage checks, or request human approval when
evidence is ambiguous. Any such method should continue to report token savings
and utility together; the Study A result shows why neither outcome can stand
in for the other.
