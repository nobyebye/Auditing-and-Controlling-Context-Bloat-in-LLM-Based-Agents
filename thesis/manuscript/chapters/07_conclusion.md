# Chapter 7: Conclusion

## 7.1 Answers to the Research Questions

This thesis studies context bloat in the automatically constructed,
model-visible context of LLM-based agents. Runtime auditing is the method:
each client-side model request is represented as ordered, source-attributed
segments, and detection, measurement, annotation, and mitigation evidence are
kept separate. The empirical design combines a controlled perturbation study,
an independently annotated natural-trace study, and a counterfactual
mitigation study.

**RQ1 asks how accurately provenance-aware heuristic signals detect and
localize independently annotated context bloat in natural agent traces.**
Study A found perfect agreement with 1,122 injected labels, but those labels
were generated from the same controlled metadata used by the detector. This
result verifies the internal operation of capture, segmentation, rule
application, and localization; it is not an estimate of natural-trace
accuracy. RQ1 requires task-macro precision, recall, F1, and localization
accuracy against the two-annotator Study B reference labels. Those real-model
results are pending in this draft, so no external detection claim is made.

**RQ2 asks how automated bloat measures agree with independent human judgments
and counterfactual removability.** Study A's perfect correlation is similarly
an internal consistency result because the measured and injected ratios share
the controlled label construction. Version 1.2 instead compares the detected
token ratio directly with the adjudicated human `remove` ratio using Spearman
correlation, mean absolute error, calibration slope, and Bland-Altman bias. A
separate replay labels a segment counterfactually removable only when its
deletion preserves success in both fixed repetitions. Until those real
annotations and replays are complete, RQ2 remains empirically unanswered
outside the controlled benchmark.

**RQ3 asks which bloat sources and patterns are observed across controlled and
naturalistic workflows.** In Study A, tool-output segments had the highest mean
injected-bloat ratio (0.500), followed by retrieval (0.487) and memory (0.468).
This ranking describes the designed fixtures and is not evidence that tool
output is universally the dominant source. The final answer to RQ3 will report
controlled injected ratios and natural-trace human-reference ratios as
separate evidence blocks, with task-cluster uncertainty and effect sizes.

**RQ4 asks what token and cost savings, and what task-performance trade-offs,
arise from provenance-aware mitigation compared with prompt compression.**
Study A establishes a mean token reduction of 48.85% (95% CI [42.67%, 55.31%])
for its controlled source-aware intervention. It also observes a task-success
difference of -6.11 percentage points (95% CI [-12.22, -0.56]). Thus,
non-inferiority is not established, and the evidence is consistent with
performance degradation. The comparative answer requires Study C's
unmodified, provenance-aware, and budget-matched LLMLingua-2 arms. No
comparative effect is claimed before those real-model results and blinded
outcome judgments are frozen.

These answers demonstrate why context auditing, bloat detection, and context
control must not be collapsed into one success claim. A pipeline can behave
exactly as designed on injected patterns without having established external
detection validity. An intervention can also reduce tokens substantially while
reducing task success. Both distinctions are substantive findings rather than
presentation caveats.

## 7.2 Contributions and Future Directions

The first contribution is a provenance-aware conceptual model of context
bloat. It distinguishes source type from bloat type and separates injected
perturbations, heuristic indicators, human reference annotations, and
counterfactual outcomes. This vocabulary prevents detector output from being
silently promoted to ground truth.

The second contribution is a runtime auditing framework that records the
client-side model request. Version 1.2 represents messages, separate system
instructions, tool definitions, generation parameters, and response format in
a `ModelRequestEnvelope`. A redacted provider request record and canonical
hash make framework-to-provider transformations auditable while keeping the
claim within the observable client boundary.

The third contribution is an executable and reproducible research artifact.
The implementation separates domain models, application use cases, ports, and
framework, provider, storage, and compression adapters. Each run receives a
unique directory and a manifest containing code, configuration, dataset,
model, seed, dependency, usage, failure, and file-hash provenance. Schema 1.1
remains readable for the frozen Study A archive, while schema 1.2 writes the
separated evidence namespaces.

The fourth contribution is a three-part empirical design. Study A supplies a
controlled perturbation benchmark with 1,188 completed task runs and 1,596
invocation traces. Study B adds 60 held-out public tasks executed through
LangChain and Custom ReAct, full-overlap double-blind segment annotation, and
agreement analysis. Study C adds 108 counterfactual replays and 180
budget-matched mitigation replays. This design turns the limitation exposed by
Study A into a directly testable validation protocol.

The fifth contribution is a utility-aware evaluation of mitigation. Every
deletion or compression remains linked to a source segment, and the analysis
reports token, cost, latency, and task success separately. Non-inferiority
sensitivity analyses at -2, -5, and -10 percentage points make the practical
tolerance visible instead of hiding it behind a single compression score.

The immediate remaining work is empirical rather than architectural. The
protocol package must receive an externally timestamped OSF registration
before paid test calls are enabled. Two annotators must then complete the
hidden Study B context labels and the condition-blind Study C outcome labels.
Only after adjudication, agreement analysis, and evidence freezing should the
abstract, graphical abstract, and final RQ wording be updated with Study B and
Study C numerical results.

Further research should evaluate additional providers, models, frameworks,
languages, retrieval systems, memory policies, and live tools. Semantic
duplicate detection, temporal validity, structured tool compression, and
multi-segment counterfactuals are especially important extensions. The central
engineering principle should remain unchanged: context should be transformed
only through auditable decisions whose efficiency gains and utility costs are
measured together.
