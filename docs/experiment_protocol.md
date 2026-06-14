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

The default pilot experiment matrix is stored in `configs/pilot.json`. The
controlled input material is stored in `datasets/controlled_synthetic/`:

- `tasks.json` defines retrieval, memory, and tool-use tasks.
- `policy_docs.json` defines the local retrieval corpus.
- `memory_items.json` defines the controlled conversation history/memory input.

- `baseline`
- `retrieval_top1`
- `retrieval_top3`
- `retrieval_duplicate`
- `retrieval_irrelevant`
- `retrieval_duplicate_mitigated`
- `retrieval_irrelevant_mitigated`
- `memory_full`
- `memory_duplicate`
- `memory_duplicate_mitigated`
- `tool_use`
- `tool_repeated_output`
- `tool_repeated_output_mitigated`
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
- Near-Duplicate Segment Count: repeated or highly overlapping segments based
  on deterministic token-set similarity.
- Irrelevant Context Filter: retrieval or memory segments with low overlap
  against the current user query.
- Estimated Cost Proxy: token-based approximation of request cost impact.

## Mitigation Evaluation

Compare original traces against mitigated traces. Report token reduction,
redundancy reduction, number of removed or compressed segments, and lightweight
task performance. The mitigation goal is to reduce unnecessary context without
significantly reducing answer usefulness.

The current implementation evaluates three conservative strategies over final
task invocations:

- exact duplicate removal
- near-duplicate removal
- irrelevant retrieval/memory filtering

In addition, the pilot includes controlled mitigated configurations where the
agent receives a reduced model-visible context before answering. These
configuration pairs are reported in `mitigation_pairs` inside the JSON summary.

## Outputs

- JSONL traces for every LLM invocation.
- JSON summary grouped by configuration and workflow family.
- CSV tables for thesis result tables.
- SVG charts for first-pass thesis figures.
- Mitigation reports with removed segments, removed tokens, source categories,
  and token reduction ratio.
- Mitigation summary includes original task success rate, post-mitigation
  success proxy rate, and success-preservation proxy rate among originally
  successful tasks.

## Repetition Strategy

Use 8-12 tasks per workflow family in the full thesis study and at least three
repetitions per configuration. The included pilot can remain smaller and should
validate the trace format, bloat metrics, localization logic, and mitigation
pipeline before the full experiment.
