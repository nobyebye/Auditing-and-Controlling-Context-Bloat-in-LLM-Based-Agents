# Chapter Outline

## Chapter 1: Introduction

Introduce automatically constructed context in LLM agents and motivate context
bloat as the central problem. Explain why bloated context matters for cost,
latency, reliability, transparency, and debugging. State the thesis question,
research questions, and contributions.

## Chapter 2: Background and Related Work

Cover LLM agents, tool use, retrieval-augmented generation, memory mechanisms,
conversation history, prompt/context management, observability, provenance, and
prior work related to context efficiency or redundancy.

## Chapter 3: Conceptual Model of Context Bloat

Define automatically constructed context, model-visible context, context
segment, context source, and context bloat. Present a taxonomy of bloat patterns
such as duplicate retrieval, repeated tool traces, stale memory, irrelevant
conversation history, oversized retrieved passages, and framework overhead.

## Chapter 4: Runtime Tracing and Bloat Localization

Describe the instrumentation layer, trace format, provenance schema, segment
labeling rules, and localization method. Explain how the auditor connects bloat
patterns to source categories such as memory, retrieval, tool, conversation
history, and framework content.

## Chapter 5: Measuring Context Bloat

Define the quantitative metrics: Redundancy Ratio, Unique Information Ratio,
Context Growth Rate, Source Contribution Ratio, Duplicate Segment Count,
Source Dominance, and estimated token/cost impact. Explain how each metric is
computed and interpreted.

## Chapter 6: Experimental Setup

Describe agent implementations, providers/models, workflow families,
configurations, tasks, repetition strategy, and task performance checks.

## Chapter 7: Empirical Results: Sources and Patterns of Bloat

Analyze where context bloat appears, which sources contribute most, how context
grows across invocations, and which workflow patterns are most vulnerable.

## Chapter 8: Mitigation Case Study

Evaluate simple mitigation methods such as exact duplicate removal, irrelevant
memory filtering, or tool-output compression. Compare context reduction,
redundancy reduction, and task performance before and after mitigation.

## Chapter 9: Discussion and Conclusion

Answer the research questions, discuss developer implications, limitations,
threats to validity, and future work. Emphasize that runtime auditing is the
methodological foundation, while context bloat is the main research problem.
