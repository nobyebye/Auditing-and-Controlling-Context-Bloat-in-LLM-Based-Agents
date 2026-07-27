# Thesis Proposal

## Title

**Runtime Auditing of Context Bloat in LLM-Based Agents: Detection,
Measurement, and Mitigation Evaluation**

Chinese reference title: **面向基于大语言模型智能体的上下文膨胀检测、量化与缓解：一种运行时审计方法**

## Summary

LLM-based agents automatically assemble model-visible context from
instructions, user input, retrieved documents, conversational memory, tool
definitions and results, and intermediate traces. This context can accumulate
duplicate, irrelevant, stale, or unnecessarily verbose material. The thesis
studies this context-bloat problem through provenance-aware runtime auditing.

The research distinguishes four evidence levels: injected perturbations,
heuristic indicators, independent human reference annotations, and
counterfactual removability. Runtime tracing and the provenance schema are the
measurement infrastructure; independently validated detection and
utility-aware mitigation are the empirical objectives.

## Research Questions

**RQ1:** How accurately can provenance-aware heuristic signals detect and
localize independently annotated context bloat in natural LLM-agent traces?

**RQ2:** To what extent do automated context-bloat measures agree with
independent human judgments and counterfactual removability?

**RQ3:** What bloat sources and patterns are observed across retrieval, memory,
and tool workflows under controlled and naturalistic conditions?

**RQ4:** What token and cost savings, and what task-performance trade-offs,
arise from provenance-aware mitigation compared with prompt compression?

## Contributions

1. A provenance-linked taxonomy that distinguishes bloat type, context source,
   and evidence origin.
2. A versioned runtime auditing framework that records client-side request
   envelopes, provider payload hashes, source segments, metrics, and
   interventions.
3. A controlled perturbation benchmark for testing internal pipeline
   consistency.
4. An independently annotated natural-trace validation study using retrieval,
   memory, and tool-use tasks.
5. A counterfactual and utility-aware mitigation evaluation against a
   budget-matched LLMLingua-2 baseline.

## Method

The empirical design contains three studies. Study A retains the existing
controlled benchmark and interprets its perfect injected-label results only as
internal consistency. Study B runs 60 held-out public tasks from HotpotQA,
LongMemEval, and BFCL through LangChain and Custom ReAct paths. Two annotators
independently label every final context while framework identity, detector
flags, source labels, model output, and automatic scores are hidden.

Study C selects segment-level counterfactuals from the adjudicated Study B
contexts and compares original, candidate-removal, and necessary-segment
removal requests. A separate replay compares unmodified context,
provenance-aware mitigation, and LLMLingua-2 under equal retained-token
budgets. Token, cost, latency, automatic score, and blind human task success
are reported together.

The independent analysis unit is `task_id`. Confidence intervals use
task-cluster hierarchical bootstrap, and task success is checked with a
task-clustered GEE sensitivity analysis. The real held-out calls are gated by a
frozen, externally timestamped OSF protocol and a shared limit of 500 HTTP
attempts.

## Expected Scope

The thesis does not claim to observe provider-internal prompt transformations
or to build a universal context optimizer. It evaluates a client-side,
provenance-aware engineering method in a fixed set of workflows, datasets, and
model conditions. Final claims about natural-trace accuracy and mitigation
depend on the registered Study B and Study C results.
