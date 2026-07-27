# Chapter Outline

Working title: **Runtime Auditing of Context Bloat in LLM-Based Agents:
Detection, Measurement, and Mitigation Evaluation**

## Chapter 1: Introduction

Motivates context bloat in automatically constructed agent context, defines the
four research questions, introduces the three-study evidence structure, and
states the conceptual, engineering, and empirical contributions.

Sections: Background and Motivation; Research Problem and Objectives; Research
Questions; Contributions and Thesis Structure.

## Chapter 2: Background and Related Work

Connects agent context construction, long-context behavior, retrieval and
memory evaluation, prompt compression, observability, and request telemetry.
It positions HotpotQA, LongMemEval, BFCL, LLMLingua-2, and OpenTelemetry
relative to the research gap.

Sections: Context Construction in LLM-Based Agents; Context Bloat and Context
Management; Agent Observability and Runtime Auditing; Research Gap.

## Chapter 3: Context Bloat Model and Auditing Framework

Defines the bloat taxonomy and the separate injected, heuristic,
human-reference, and counterfactual evidence namespaces. It presents the
request envelope, provider payload record, provenance metrics, detection,
localization, and protected-segment mitigation.

Sections: Definition and Taxonomy; Provenance and Measurement Model; Runtime
Auditing Framework; Detection, Localization, and Mitigation.

## Chapter 4: Research Methodology

Specifies Study A (controlled perturbations), Study B (independently annotated
natural traces), and Study C (counterfactual and compression comparison). It
documents datasets, two execution paths, request capture, blind annotation,
task-cluster statistics, OSF gating, and the 500-call budget.

Sections: Experimental Design; Agent Implementations and Environment;
Evaluation and Statistical Analysis; Human Evaluation and Validity.

## Chapter 5: Empirical Results

Reports Study A as controlled pipeline consistency and reserves external
detection, measurement, and natural source claims for the registered Study B
evidence. Controlled and natural results remain separate throughout.

Sections: Detection and Localization; Measurement and Source Analysis;
Execution-Path and Stress-Case Comparison; RQ1-RQ3 Evidence Summary.

## Chapter 6: Mitigation Evaluation and Discussion

Reports Study A token savings together with its observed degradation risk,
defines counterfactual necessity, and specifies the equal-budget Study C
comparison with LLMLingua-2. It then discusses capture boundaries, provenance,
deployment implications, and validity limitations.

Sections: Mitigation Effectiveness; Counterfactual Necessity and
Interpretation; Engineering Implications; Limitations and Future Work.

## Chapter 7: Conclusion

Answers each RQ using effect estimates, uncertainty, scope, and evidence
status. Pending Study B/C values are not replaced by controlled or mock
results.

Sections: Answers to the Research Questions; Contributions and Future
Directions.

## Back Matter

References are followed by appendices for the taxonomy and schema; datasets and
configurations; additional statistics; reproduction instructions; and the
human annotation protocols.
