# Thesis Proposal

## Title

**Auditing and Controlling Context Bloat in LLM-Based Agents**

Alternative title: **Detecting, Measuring, and Mitigating Context Bloat in LLM-Based Agents**

Chinese title: **面向 LLM 智能体上下文膨胀的检测、量化与缓解研究**

## Summary

This thesis studies context bloat in LLM-based agents. The broader research
object is automatically constructed context: the model-visible context assembled
at runtime from system prompts, user input, retrieval, memory, tool traces,
conversation history, and framework-generated content. The central problem is
that this automatically constructed context can become bloated through
redundant, stale, irrelevant, or repeated content.

The thesis uses runtime tracing, context auditing, and a provenance schema as
the methodological foundation. These tools are not the final goal by themselves.
They are used to detect, localize, measure, and mitigate context bloat across
controlled LLM-agent workflows.

## Research Questions

RQ1: How can context bloat be detected and localized in LLM-based agents?

RQ2: How can context bloat be quantitatively measured?

RQ3: What are the main sources and patterns of context bloat?

RQ4: Can context bloat be mitigated without significantly reducing task
performance?

## Contributions

1. A taxonomy of context bloat patterns in automatically constructed agent
   context.
2. A set of quantitative metrics for context redundancy and growth, including
   Redundancy Ratio, Unique Information Ratio, Context Growth Rate, and Source
   Contribution Ratio.
3. A runtime tracing and auditing toolkit that captures model-visible context
   before each LLM invocation and localizes bloat by source type.
4. An empirical analysis of bloat sources across retrieval, memory, tool-use,
   conversation-history, and combined agent workflows.
5. A simple mitigation method, such as duplicate removal, irrelevant memory
   filtering, or tool-output compression, evaluated for token reduction and task
   performance impact.

## Method

The thesis will evaluate a LangChain-based agent and a lightweight custom
ReAct-style agent. Workflow families include retrieval QA, multi-step tool use,
and memory-based multi-turn tasks. Each workflow will be run under controlled
configurations such as baseline, retrieval-enabled, memory-enabled, tool-use,
combined retrieval-memory-tool, guard detection, and mitigation mode.

The runtime auditor captures every model-visible invocation, segments the
context, labels each segment by source type, and computes bloat metrics. The
analysis then identifies which source categories contribute most to bloat and
which workflow patterns produce the fastest growth.

Mitigation is evaluated in a controlled way. The thesis will compare original
context against reduced context and report token reduction, redundancy
reduction, and lightweight task performance. The goal is not to build a broad
optimization system, but to test whether simple bloat controls can reduce
unnecessary context without clearly harming utility.
