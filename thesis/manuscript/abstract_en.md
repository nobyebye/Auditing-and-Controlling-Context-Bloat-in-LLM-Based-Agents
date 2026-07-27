# Abstract

**Status:** Draft v0.5. Study B and Study C real-model results are pending.

LLM-based agents construct model-visible context at runtime from system
instructions, user messages, retrieved documents, conversational memory, tool
definitions and outputs, and intermediate traces. This process can introduce
context bloat: content that is redundant, irrelevant, stale, or unnecessarily
verbose for a particular task. This thesis investigates how provenance-aware
runtime auditing can detect, measure, localize, and control such content
without treating token reduction as evidence of preserved utility.

The thesis develops a versioned provenance schema and a Python auditing
framework that capture the client-side serialized request before each model
invocation. The framework records ordered segments, source attribution, token
counts, normalized hashes, request-payload hashes, detector outputs,
annotations, counterfactual outcomes, and mitigation decisions. Its evidence
model separates injected perturbations, heuristic indicators, independent
human reference labels, and counterfactual removability.

The empirical design contains three studies. Study A is a controlled
perturbation benchmark covering retrieval, memory, and tool workflows through
LangChain and Custom ReAct execution paths. It contains 1,188 completed task
runs and 1,596 invocation traces. Its perfect agreement with 1,122 injected
labels demonstrates pipeline consistency, not real-world detection accuracy.
Study B adds 60 held-out public tasks, 120 natural final contexts, and
full-overlap double-blind segment annotation. Study C adds paired
counterfactual deletion and a budget-matched comparison between
provenance-aware mitigation and LLMLingua-2. The Study B and Study C software
has passed mock end-to-end validation; real calibration and held-out execution
remain gated by the initial registration and calibration addendum.

In Study A, the mitigation reduced context tokens by 48.85% on average (95% CI
[42.67%, 55.31%]). Task success changed by -6.11 percentage points (95% CI
[-12.22, -0.56]). Token reduction was therefore established for the controlled
fixtures, but task-performance non-inferiority was not established, and the
observed evidence was consistent with degradation. Tool output had the highest
injected-bloat ratio under the designed fixtures, but this ranking is not
generalized to natural agents.

The thesis contributes a provenance-aware auditing framework, a controlled
perturbation benchmark, and an independently testable protocol for natural
trace validation and utility-aware mitigation. Final claims about external
detection accuracy, human agreement, counterfactual removability, and
compression baselines depend on the pending registered studies.

**Keywords:** LLM agents; context bloat; runtime auditing; context provenance;
retrieval-augmented generation; agent memory; tool use
