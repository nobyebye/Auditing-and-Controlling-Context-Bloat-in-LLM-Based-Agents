# Related Work for Context Bloat in LLM-Based Agents

This note organizes implementation references and papers for the thesis:

**Auditing and Controlling Context Bloat in LLM-Based Agents**

The main thesis framing is:

> Automatically constructed context is the research object; context bloat is the
> central problem. Runtime tracing, context auditing, and provenance labeling are
> the method used to detect, localize, measure, and mitigate bloat.

## Implementation References

| Project | Link | Why It Matters |
|---|---|---|
| AgentFootprint | https://github.com/footprintjs/agentfootprint | Closest implementation reference for tracing what context is injected into agent LLM calls. Useful for model-visible context capture and trace design. |
| Opik | https://github.com/comet-ml/opik | Mature observability platform for LLM apps, RAG, and agentic systems. Useful for production-grade tracing, evaluation, dashboards, and monitoring design. |
| RagaAI Catalyst | https://github.com/raga-ai-hub/RagaAI-Catalyst | Runtime tracing and debugging for agents, tools, timelines, and execution graphs. Useful for visualizing multi-step agent execution. |
| Cordum | https://github.com/cordum-io/cordum | Governance-oriented agent control with policies, approval gates, and audit trails. Useful if the thesis discusses how auditing can support control. |
| MCP Token Auditor | https://github.com/Ismail-2001/mcp-token-auditor | Small but thematically close token/context auditing project, especially for MCP, context-window usage, and token attribution. |

## Core Papers to Use

### 1. Context Bloat Motivation and Long-Context Failure

**Lost in the Middle: How Language Models Use Long Contexts**  
Nelson F. Liu et al., TACL 2024.  
Link: https://arxiv.org/abs/2307.03172

Use this as a central motivation paper. It shows that longer context is not
automatically better: model performance can degrade when relevant information is
buried in the middle of long inputs. This directly supports the argument that
context bloat is not only a cost issue, but also a reliability and usability
issue.

**RULER: What's the Real Context Size of Your Long-Context Language Models?**  
Cheng-Ping Hsieh et al., 2024.  
Link: https://arxiv.org/abs/2404.06654

Use this to support evaluation design. RULER argues that simple
needle-in-a-haystack tests are too shallow and proposes more complex long-context
tests. This is useful when justifying why your thesis should measure growth,
redundancy, and task impact, rather than only counting tokens.

**LongBench: A Bilingual, Multitask Benchmark for Long Context Understanding**  
Yushi Bai et al., 2023.  
Link: https://arxiv.org/abs/2308.14508

Use this for background on long-context evaluation. It is less directly about
agents, but useful for explaining why long context understanding is hard across
QA, summarization, few-shot learning, and code tasks.

### 2. Automatically Constructed Context Sources

**ReAct: Synergizing Reasoning and Acting in Language Models**  
Shunyu Yao et al., 2022.  
Link: https://arxiv.org/abs/2210.03629

Use this as the main foundation for tool-use traces and intermediate reasoning
trajectories. ReAct-style agents naturally create repeated observations,
actions, and scratchpad traces, which are likely sources of context bloat.

**Toolformer: Language Models Can Teach Themselves to Use Tools**  
Timo Schick et al., 2023.  
Link: https://arxiv.org/abs/2302.04761

Use this for the tool-use background. It helps explain why tool outputs become
part of the model-visible context and why tool descriptions/results can
increase prompt size.

**Generative Agents: Interactive Simulacra of Human Behavior**  
Joon Sung Park et al., 2023.  
Link: https://arxiv.org/abs/2304.03442

Use this for memory-based agents. It provides a well-known architecture where
observations, memory, reflection, and planning are stored and retrieved over
time. This is highly relevant for memory bloat and stale/irrelevant context.

**Reflexion: Language Agents with Verbal Reinforcement Learning**  
Noah Shinn et al., 2023.  
Link: https://arxiv.org/abs/2303.11366

Use this for episodic memory and self-reflection traces. Reflexion stores
verbal feedback in memory, which is a strong example of useful context that can
also accumulate and become bloated.

### 3. Retrieval and RAG as Context Bloat Sources

**Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks**  
Patrick Lewis et al., 2020.  
Link: https://arxiv.org/abs/2005.11401

Use this as the foundational RAG paper. It explains why retrieved passages are
added to model input and why provenance matters. Your thesis can build on this
by asking when retrieved context becomes excessive, redundant, or irrelevant.

**RAGAS: Automated Evaluation of Retrieval Augmented Generation**  
Shahul Es et al., 2023.  
Link: https://arxiv.org/abs/2309.15217

Use this for evaluation ideas around context relevance and faithfulness. It can
inspire the task-performance side of your mitigation evaluation.

**Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection**  
Akari Asai et al., 2023.  
Link: https://arxiv.org/abs/2310.11511

Use this to justify adaptive retrieval. It argues against indiscriminately
retrieving a fixed number of passages. This connects directly to retrieval bloat:
not every task needs the same amount of retrieved context.

**RECOMP: Improving Retrieval-Augmented LMs with Compression and Selective Augmentation**  
Fangyuan Xu, Weijia Shi, Eunsol Choi, 2023.  
Link: https://arxiv.org/abs/2310.04408

Use this as one of the closest mitigation papers. RECOMP compresses retrieved
documents and can return an empty string when retrieved content is irrelevant.
This maps well to your mitigation question.

### 4. Measuring and Mitigating Redundant Context

**LLMLingua: Compressing Prompts for Accelerated Inference of Large Language Models**  
Huiqiang Jiang et al., 2023.  
Link: https://arxiv.org/abs/2310.05736

Use this as a major prompt-compression baseline. It is relevant to mitigation:
reduce prompt length while preserving task performance.

**LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression**  
Huiqiang Jiang et al., 2023.  
Link: https://arxiv.org/abs/2310.06839

Use this because it explicitly targets long-context scenarios and discusses
cost, latency, and performance. It is a strong match for the mitigation part of
your thesis.

**Compressing Context to Enhance Inference Efficiency of Large Language Models**  
Yucheng Li, Bo Dong, Chenghua Lin, Frank Guerin, 2023.  
Link: https://arxiv.org/abs/2310.06201

Use this for redundancy-aware context pruning. The Selective Context method is
very close to your idea of removing unnecessary context while preserving
performance.

**Characterizing Prompt Compression Methods for Long Context Inference**  
Siddharth Jha et al., 2024.  
Link: https://arxiv.org/abs/2407.08892

Use this as a comparison paper. It evaluates extractive compression,
summarization-based compression, and token pruning. Good for explaining why
your mitigation should start conservatively with simple duplicate removal or
source filtering.

### 5. Agent Observability and Auditing

**AgentOps: Enabling Observability of LLM Agents**  
Liming Dong, Qinghua Lu, Liming Zhu, 2024.  
Link: https://arxiv.org/abs/2411.05285

Use this to situate your tracing/auditing tool in the AgentOps literature. It
is less about context bloat specifically, but it supports the need to trace
agent artifacts throughout execution.

**AgentScope: A Flexible yet Robust Multi-Agent Platform**  
Dawei Gao et al., 2024.  
Link: https://arxiv.org/abs/2402.14034

Use this for agent framework background. It is helpful when discussing how
frameworks manage messages, tools, memory, and monitoring.

## Emerging but Optional Papers

These are very close to the exact phrase "context bloat" or tool-selection
bloat, but some are newer or less established. Use them carefully, usually in a
"recent/emerging work" paragraph rather than as the main theoretical foundation.

**RAG-MCP: Mitigating Prompt Bloat in LLM Tool Selection via Retrieval-Augmented Generation**  
Tiantian Gan, Qiyao Sun, 2025.  
Link: https://arxiv.org/abs/2505.03275

Very relevant if your tool registry/tool-description bloat becomes a case
study. It is about reducing prompt bloat when many MCP tools are available.

**Active Context Compression: Autonomous Memory Management in LLM Agents**  
Nikhil Verma, 2026.  
Link: https://arxiv.org/abs/2601.07190

Very close to your exact topic because it explicitly discusses context bloat in
long-horizon LLM agents. Treat it as emerging related work unless it becomes
peer-reviewed.

**Contextual Memory Virtualisation: DAG-Based State Management and Structurally Lossless Trimming for LLM Agents**  
Cosmo Santoni, 2026.  
Link: https://arxiv.org/abs/2602.22402

Relevant for long-running sessions and trimming mechanical bloat such as raw
tool outputs and metadata. Useful for discussion and future work.

## Recommended Thesis Framing

For the final related work chapter, use four groups:

1. LLM agents and automatically constructed context: ReAct, Toolformer,
   Generative Agents, Reflexion.
2. Long-context limitations and bloat motivation: Lost in the Middle, RULER,
   LongBench.
3. Retrieval, memory, and context quality: RAG, RAGAS, Self-RAG, RECOMP.
4. Context compression and mitigation: LLMLingua, LongLLMLingua, Selective
   Context, prompt-compression characterization.

AgentOps and the implementation repositories should be used to justify the
engineering artifact and observability angle, not as the core problem statement.

## Most Important Starting Set

If time is limited, start with these eight papers first:

1. Lost in the Middle
2. RULER
3. ReAct
4. Generative Agents
5. Retrieval-Augmented Generation
6. Self-RAG
7. RECOMP
8. LongLLMLingua

This set covers motivation, agent context sources, retrieval/memory behavior,
and mitigation.
