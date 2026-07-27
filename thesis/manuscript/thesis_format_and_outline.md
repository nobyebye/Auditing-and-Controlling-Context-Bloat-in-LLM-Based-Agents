# Thesis Format and Outline

## Document Identity

**English title:** Detecting, Measuring, and Mitigating Context Bloat in
LLM-Based Agents: A Runtime Auditing Approach

**Chinese reference title:** 面向基于大语言模型智能体的上下文膨胀检测、量化与缓解：一种运行时审计方法

**Author:** Guochen Li

**Degree programme:** Master's Programme in Computer Science

**Faculty:** Faculty of Science, University of Helsinki

**Language:** English

**Working status:** Formal thesis draft v0.4; external validation pending

## Template and Content Contract

`thesis/materials/Guochen_Li.docx` is the current formatting authority.
Markdown remains the version-controlled content source.

- Target main-text length: approximately 44-48 pages, excluding references and
  appendices.
- English abstract length: approximately 250-350 words after Study B/C result
  insertion.
- Markdown headings map to the template's Heading 1, Heading 2, and Heading 3
  styles.
- Citations use Pandoc-style BibTeX keys and are rendered as IEEE numeric
  references in Word.
- Figures and tables use stable labels and must be linked to a run artifact or
  generation source.
- The three core figures are the research overview, the Study A/B/C workflow,
  and the graphical abstract. Their final numerical content is frozen only
  after Study B/C.
- Page geometry, fonts, cover, abstract, headings, headers, footers, and fields
  are inherited from `thesis/materials/Guochen_Li.docx`.
- Degree programme or course metadata, supervisor, and date remain blank until
  the author supplies them.

## Text and Evidence Management

- Markdown files under `thesis/manuscript/` are the writing source of truth.
- Temporary Word/PDF builds stay under `thesis/build/`; submission candidates
  stay under `thesis/releases/`.
- Study A claims trace to the immutable schema-1.1 bundle and run record.
- Study B/C claims must trace to a schema-1.2 bundle, two original annotation
  files, adjudication output, evidence JSON, protocol hash, and OSF timestamp.
- Mock results validate software only and must never appear as thesis evidence.
- The observable boundary is the client-side serialized request, not
  provider-internal processing.
- RQ conclusions are expressed with estimates, confidence intervals, sample
  size, and scope rather than a bare `Supported` or `Inconclusive` label.

## Research Questions

**RQ1:** How accurately can provenance-aware heuristic signals detect and
localize independently annotated context bloat in natural LLM-agent traces?

**RQ2:** To what extent do automated context-bloat measures agree with
independent human judgments and counterfactual removability?

**RQ3:** What bloat sources and patterns are observed across retrieval, memory,
and tool workflows under controlled and naturalistic conditions?

**RQ4:** What token and cost savings, and what task-performance trade-offs,
arise from provenance-aware mitigation compared with prompt compression?

## Chapter Plan

| Chapter | Main sections | Target pages | Primary function |
| --- | --- | ---: | --- |
| 1. Introduction | 1.1-1.4 | 4-5 | Define the problem, evidence hierarchy, RQs, and contributions. |
| 2. Background and Related Work | 2.1-2.4 | 7-8 | Connect context construction, management, compression, and observability. |
| 3. Context Bloat Model and Auditing Framework | 3.1-3.4 | 8-9 | Present taxonomy, evidence namespaces, request capture, metrics, and mitigation. |
| 4. Research Methodology | 4.1-4.4 | 7-8 | Define Study A/B/C, annotation, statistical analysis, and validity controls. |
| 5. Empirical Results | 5.1-5.4 | 8-9 | Separate controlled consistency from independently annotated natural evidence. |
| 6. Mitigation Evaluation and Discussion | 6.1-6.4 | 7-8 | Report efficiency and utility together, then discuss implications and limits. |
| 7. Conclusion | 7.1-7.2 | 2-3 | Answer the RQs with scoped evidence and summarize contributions. |

## Back Matter

- References
- Appendix A: Context Bloat Taxonomy and Trace Schema
- Appendix B: Datasets, Conditions, and Configurations
- Appendix C: Additional Statistical Results
- Appendix D: Reproduction Instructions
- Appendix E: Human Annotation and Adjudication Protocol

Appendices contain replication detail, full tables, schemas, and review forms.
They do not duplicate the central argument.

## Current Evidence Vocabulary

**Study A: controlled perturbation evidence**

- 1,596 invocation traces and 1,188 completed task runs.
- Perfect agreement with 1,122 injected labels: internal pipeline consistency,
  not natural-trace accuracy.
- Mean injected-bloat ratio: tool 0.500, retrieval 0.487, memory 0.468. This is
  a fixture-specific ranking.
- Mean token reduction: 48.85%, 95% CI [42.67%, 55.31%].
- Task-success difference: -6.11 percentage points, 95% CI [-12.22, -0.56].
- Interpretation: token reduction is established for the controlled fixtures;
  non-inferiority is not established, and the evidence is consistent with
  performance degradation.

**Study B/C: pending external evidence**

- Study B design: 60 held-out tasks, two execution paths, 120 final contexts,
  and two independent annotators with full overlap.
- Study C design: 108 counterfactual calls and 180 mitigation-comparison calls.
- Real result fields remain empty until OSF registration, paid execution,
  annotation, adjudication, and evidence freezing are complete.
