# Experiment Protocol

## Implementations

- LangChain-based agent: primary implementation, continuing the seminar work.
- Custom ReAct-style agent: controlled second implementation with retrieval,
  memory, conversation history, and tool-use behavior.

## Workflow Families

- Retrieval QA: controlled policy questions over a small local document set.
- Multi-step tool use: deterministic calculator or structured lookup tasks with
  repeated tool traces.
- Memory turns: prompts that require restored conversation history or memory
  summaries.
- Combined workflows: retrieval plus memory plus tool traces to test compound
  bloat.

## Configurations

- `baseline`
- `retrieval_top1`
- `retrieval_top3`
- `retrieval_duplicate`
- `memory_full`
- `memory_duplicate`
- `tool_use`
- `tool_repeated_output`
- `retrieval_memory_tool`
- `bloat_detection`
- `mitigation_duplicate_removal`
- optional `mitigation_memory_filtering`
- optional `mitigation_tool_compression`

## Bloat Metrics

- Redundancy Ratio: proportion of context tokens belonging to repeated or
  near-duplicate segments.
- Unique Information Ratio: proportion of context tokens that remain after
  duplicate or redundant segments are collapsed.
- Context Growth Rate: relative token increase across successive invocations.
- Source Contribution Ratio: share of total or redundant tokens contributed by
  each source type.
- Duplicate Segment Count: number of repeated segments detected by normalized
  hashes.
- Source Dominance: flag for cases where one automatic source dominates the
  prompt.
- Estimated Cost Proxy: token-based approximation of request cost impact.

## Mitigation Evaluation

Compare original traces against mitigated traces. Report token reduction,
redundancy reduction, number of removed or compressed segments, and lightweight
task performance. The mitigation goal is to reduce unnecessary context without
significantly reducing answer usefulness.

## Repetition Strategy

Use 8-12 tasks per workflow family in the full thesis study and at least three
repetitions per configuration. The included pilot can remain smaller and should
validate the trace format, bloat metrics, localization logic, and mitigation
pipeline before the full experiment.
