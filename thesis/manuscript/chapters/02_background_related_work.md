# Chapter 2: Background and Related Work

## 2.1 Context Construction in LLM-Based Agents

An LLM-based agent combines a language model with an execution loop and
external capabilities. The model is asked not only to produce a final answer,
but also to select actions, interpret observations, update state, or decide
what information should be obtained next. The surrounding application turns
these decisions into model calls, retrieval requests, memory operations, and
tool invocations. As a result, an agent's effective input is produced jointly
by the model, the framework, and the environment.

ReAct is a representative example of this interaction pattern. It interleaves
reasoning traces with task-specific actions and adds observations from external
sources back into the trajectory [@yao2022react]. This design supports planning
and exception handling because a later model call can inspect earlier actions
and observations. From the perspective of context construction, however, every
step can also enlarge the next input. If an agent retains the full trajectory,
the model may repeatedly receive instructions, past reasoning, action records,
and tool results. Toolformer illustrates a related but different form of tool
use: a model learns when to call an API, how to provide its arguments, and how
to incorporate its result into subsequent token prediction
[@schick2023toolformer]. Both approaches demonstrate why tool outputs are not
merely external side effects. They become textual evidence that can influence
later model behavior and therefore belong to the model-visible context.
ToolLLM scales this interaction to a large API collection and couples tool
selection with multi-step search, illustrating how function definitions and
intermediate observations can become substantial request components
[@qin2024toolllm]. AgentBench evaluates agents across interactive environments
and reports long-horizon reasoning and instruction-following failures
[@liu2024agentbench]. Together, these systems motivate auditing both the
content accumulated by an execution loop and the task result produced from it.

Retrieval-augmented generation introduces another major context source. The
original RAG formulation combines a parametric generator with documents
retrieved from a non-parametric memory [@lewis2020rag]. Retrieval makes external
knowledge easier to update and can provide provenance for generated answers,
but it also requires a selection decision: which passages, how many, and in
what order should be included in the model input? A fixed top-*k* policy may
return overlapping passages, and a retrieved document can be topically related
without containing information needed for the current question. Retrieval
therefore creates both useful context and a possible mechanism for redundant or
low-relevance context.

Agent memory extends construction across time. Generative Agents stores
observations in a memory stream and retrieves records based on recency,
importance, and relevance; it also generates higher-level reflections that can
guide future behavior [@park2023generative]. Reflexion stores linguistic
feedback in an episodic memory buffer so that later trials can use earlier
failures and reflections without changing the model weights
[@shinn2023reflexion]. These designs show that memory is not simply conversation
history. It may include selected events, summaries, reflections, task
outcomes, or other state derived from previous interactions. The selection
policy determines whether the next invocation receives timely evidence or
stale and repeated material.

Conversation history is a simpler form of memory but presents the same
construction problem. A chat-oriented agent may append every earlier message,
retain a sliding window, or insert a summary together with selected recent
turns. Full history preserves detail but grows with the conversation. A summary
reduces size but may omit information, become stale, or overlap with raw turns
that are also retained. In either case, the runtime decides what is visible to
the model.

Framework-generated content forms a less visible source. Agent frameworks may
insert tool schemas, role instructions, formatting constraints, planning
prompts, error messages, or intermediate message wrappers. Some of this content
is stable across invocations; other parts are generated in response to the
current state. The user may never see it, and an application log may record
only the user request and final answer. This is why the unit of analysis in this
thesis is the complete input immediately before a model call rather than the
user-facing transcript.

These sources can be represented as a sequence

$$
C_i = S_i \mathbin{\|} U_i \mathbin{\|} F_i \mathbin{\|} R_i
\mathbin{\|} M_i \mathbin{\|} T_i \mathbin{\|} G_i,
$$

where $C_i$ is the context of invocation $i$ and the components denote system,
user, framework, retrieval, memory, tool, and generated-trace content. The
notation does not require every framework to concatenate literal strings in
this order. It states that the serialized model input can be decomposed into
ordered segments with provenance. This decomposition is the conceptual bridge
between agent architecture and context auditing.

## 2.2 Context Bloat and Context Management

Long-context capability is commonly described through the maximum number of
tokens a model can accept. That limit is an important deployment constraint,
but it does not measure how effectively the model uses the input. LongBench
evaluates long-context understanding across tasks such as question answering,
summarization, few-shot learning, synthetic reasoning, and code
[@bai2023longbench]. Lost in the Middle focuses more specifically on the
position of relevant information and shows that performance can deteriorate
when evidence is placed away from the beginning or end of the context
[@liu2024lost]. RULER extends simple retrieval tests with multiple needles,
multi-hop tracing, and aggregation; its results show that usable context can be
substantially smaller than an advertised context window as length and
complexity increase [@hsieh2024ruler].

These findings motivate context management but should not be conflated with
context bloat. A difficult long-context task can contain no unnecessary
information, while a short prompt can contain duplicated or irrelevant
segments. This thesis treats bloat as a property of the relationship between
content, source, invocation, and task. Context is bloated when a defined part
is avoidable under the study's criterion, not merely when the total token count
is high.

Retrieval evaluation provides useful concepts for this distinction. RAGAS
separates properties such as the relevance and focus of retrieved context from
the faithfulness and quality of the generated answer [@es2023ragas]. Self-RAG
argues that indiscriminately retrieving a fixed number of passages can reduce
quality and instead learns to retrieve and critique passages on demand
[@asai2023selfrag]. Both approaches recognize that retrieval quantity and
retrieval utility are not equivalent. In the present thesis,
low-query-relevance retrieval is one controlled bloat pattern, while source
provenance makes it possible to measure its contribution separately from
memory or tool output.
ARES adds a complementary lesson: automated RAG evaluation benefits from a
small independent human reference rather than relying only on synthetic judge
data [@saadfalcon2024ares]. This supports the present separation between
heuristic indicators and adjudicated human labels.

Several lines of work reduce context before inference. RECOMP trains
compressors for retrieved documents and supports selective augmentation,
including the option to provide no retrieved context when it is not useful
[@xu2023recomp]. Selective Context removes less informative lexical units using
self-information as a proxy [@li2023selectivecontext]. LLMLingua uses a smaller
language model to identify and compress less important prompt content under a
token budget [@jiang2023llmlingua], while LongLLMLingua adapts prompt
compression to long-context settings and accounts for document relevance and
the position of retained information [@jiang2023longllmlingua]. Jha et al.
compare prompt-compression families and show that extractive selection,
summarization, and token-level pruning have different quality and efficiency
trade-offs [@jha2024promptcompression].
Gist tokens represent a model-trained alternative that compresses reusable
instructions into a small latent prefix [@mu2023gist]. RAPTOR constructs
hierarchical summaries for retrieval across long documents
[@sarthi2024raptor]. These methods broaden context management beyond lexical
deletion, while also making clear that compression architecture and runtime
source auditing answer different questions.

LLMLingua-2 replaces the earlier coarse-to-fine pipeline with a
data-distilled token-classification approach and reports gains in compression
speed and task transfer [@pan2024llmlingua2]. It provides a relevant baseline
for this thesis because it compresses prompts without requiring the
provenance-specific rules used by the proposed mitigation. Compression quality
also depends on information preservation: evaluation should examine whether a
shortened request retains task-relevant information rather than treating
compression rate as a sufficient outcome [@lajewska2025information]. This
motivates the token-budget-matched and utility-aware comparison in Study C.
ContextCite estimates which context parts influence a generated statement and
demonstrates context pruning as one downstream application
[@cohenwang2024contextcite]. ProCut likewise prunes prompt segments through
attribution estimation and evaluates both reduction and task performance
[@xu2025procut]. These attribution-based methods are especially close to the
counterfactual motivation of this thesis, but they do not replace independent
segment annotation or provenance capture at the agent request boundary.

This compression literature is closely related to mitigation, but its
objective is not identical to runtime auditing. Compression methods generally
start with a prompt or retrieved context and produce a shorter representation.
They may optimize a token budget without identifying which agent subsystem
introduced the content or how the same material accumulated across
invocations. Conversely, a provenance auditor can localize and measure bloat
without having a strong compressor. The two approaches are complementary:
auditing establishes what should be examined and how an intervention is
evaluated, while compression or filtering supplies a possible intervention.

The distinction also affects evaluation. A compression ratio by itself cannot
show that an intervention was beneficial. A method could remove half of the
tokens by deleting the only passage that contains the answer. For this reason,
RECOMP, LLMLingua, LongLLMLingua, and Selective Context evaluate downstream
quality in addition to reduction [@xu2023recomp; @jiang2023llmlingua;
@jiang2023longllmlingua; @li2023selectivecontext]. The present study adopts the
same general principle. Study A evaluates a deliberately conservative
mitigation retrospectively, while the externally registered Study C protocol
specifies a -5 percentage-point non-inferiority margin and -2/-5/-10
percentage-point sensitivity analyses for task success.

Context management in agents adds a temporal dimension that prompt compression
does not always address. A segment can be locally useful yet become redundant
when copied into every later invocation. A memory may be accurate but stale
relative to the current user request. A verbose tool result may contain useful
fields mixed with repeated metadata. These cases motivate invocation-level
metrics for exact redundancy, near redundancy, context growth, source
contribution, and source-specific bloat.

## 2.3 Agent Observability and Runtime Auditing

Observability makes the internal behavior of an agent inspectable through
traces, metrics, and structured events. In a conventional distributed system,
observability often centers on requests, services, latency, errors, and
resource consumption. LLM agents add semantic artifacts: prompts, messages,
model responses, retrieval results, tool calls, memory state, and evaluation
scores. AgentOps describes an observability lifecycle for agent development and
operation, emphasizing monitoring and analysis of agent behavior
[@dong2024agentops]. AgentScope similarly provides a framework for building and
monitoring multi-agent applications and illustrates how message handling and
execution infrastructure become part of agent engineering
[@gao2024agentscope].

Production-oriented open-source tools reinforce this engineering direction.
AgentFootprint focuses on tracking context injected into model calls, which is
close to the invocation-boundary instrumentation used here
[@agentfootprint2026]. Opik supports
tracing, evaluation, and monitoring for LLM applications, RAG systems, and
agents [@opik2026]. RagaAI Catalyst presents agent and tool execution through
timelines and execution traces [@ragacatalyst2026]. These systems are useful
implementation references because
they demonstrate practical concerns such as trace identifiers, spans,
framework integrations, evaluation records, and visual debugging. Their
purpose, however, is broader than the specific measurement of context bloat.

OpenTelemetry's semantic conventions for generative AI systems provide a
standard vocabulary for model, request, response, usage, and agent-operation
telemetry [@opentelemetry2026genai]. These conventions improve
interoperability, but they do not define segment-level bloat evidence or
counterfactual necessity. The schema in this thesis therefore complements
general telemetry with ordered source segments, evidence provenance, and
mitigation decisions.

Two smaller projects illustrate adjacent boundaries. Cordum connects audit
trails with pre-execution policies and approval gates [@cordum2026], whereas
MCP Token Auditor focuses more narrowly on context-window use and token
attribution for tool interfaces [@mcptokenauditor2026]. They are engineering
references rather than empirical baselines, but they help distinguish
observing context, attributing its cost, and controlling agent behavior.

The term *auditing* is used in this thesis to indicate a more constrained form
of observability. A runtime audit record must answer five questions for each
model invocation:

1. What exact messages and segments were visible to the model?
2. Which source produced each segment?
3. How large was each segment and the complete context?
4. Which injected label, heuristic indicator, human annotation, or
   counterfactual outcome applied, and where?
5. Which code, configuration, dataset, model, and seed produced the record?

This definition links content provenance to experimental reproducibility.
Capturing a prompt string without a source label is insufficient for
localization. Recording source labels without the final serialized messages can
miss transformations performed by a framework. Reporting aggregate token usage
without invocation identifiers cannot reconstruct growth across a multi-step
workflow. A useful audit trace therefore needs both semantic content structure
and engineering provenance.

Privacy complicates this requirement. Full model-visible text is the most
informative trace, but it may contain user data, retrieved confidential
documents, or credentials accidentally exposed by an integration. The
framework developed for this thesis consequently treats persisted text as a
policy choice. Metrics are computed from the in-memory content, while persisted
traces can store full, redacted, or hash-only representations. Raw and
normalized hashes preserve segment identity and duplicate evidence without
requiring all text to remain available. The formal experiments use redacted
mode.

Runtime auditing also differs from application-level evaluation. RAGAS, for
example, evaluates retrieval and generation quality
[@es2023ragas], whereas the auditor in this thesis records how retrieval,
memory, tool, and framework content jointly compose an invocation. Evaluation
can be built on top of the audit record, but the trace itself is intended to be
a reusable measurement artifact. This separation is important for an
engineering thesis: capture, storage, analysis, and mitigation are distinct
components with testable interfaces.

## 2.4 Research Gap

The literature provides strong foundations for each part of the problem, but
the parts are usually studied separately. Agent architectures explain why
external observations, retrieved evidence, and memory are inserted into future
model calls. Long-context benchmarks show that greater nominal capacity does
not ensure robust use of longer inputs. RAG evaluation examines relevance and
faithfulness. Prompt-compression methods reduce tokens while measuring
downstream quality. Agent observability records complex execution behavior.
What remains less developed is an end-to-end method that connects these areas
at the level of automatically constructed context.

Table 2.1 summarizes the distinction.

| Research area | Primary object | Typical outcome | Gap addressed by this thesis |
| --- | --- | --- | --- |
| Long-context evaluation | Model behavior at increasing input lengths | Accuracy or task score by length and position | Does not localize avoidable agent context to runtime sources |
| RAG and memory quality | Retrieved or stored evidence | Relevance, faithfulness, or answer quality | Usually studies one source rather than the complete agent invocation |
| Prompt compression | A prompt or document set | Token reduction and downstream quality | Does not necessarily preserve source provenance or longitudinal growth |
| Agent observability | Calls, tools, events, and execution paths | Traces, spans, latency, errors, evaluations | Does not by itself define or validate source-level bloat metrics |
| This thesis | Complete model-visible context per invocation | Detection, localization, measurement, source analysis, and constrained mitigation | Integrates provenance, bloat metrics, reproducible runs, and utility-aware evaluation |

Three specific gaps motivate the research design. First, context-size metrics
do not explain composition. A total of 1,000 tokens can be dominated by
retrieval in one invocation and by tool output in another. Source-labeled
segments are needed to compare those cases. Second, most observed context has
no independent label indicating whether it is necessary. Controlled bloat
patterns provide a reproducible starting point for validating detection and
measurement, provided their limited external validity is acknowledged. Third,
mitigation needs a joint criterion. A reduction should be interpreted together
with task success rather than presented as an isolated efficiency gain.

Public benchmarks make it possible to address the independence gap without
inventing every task and label inside the detector. HotpotQA supplies
multi-hop retrieval questions and supporting documents [@yang2018hotpotqa].
LongMemEval tests long-term conversational memory across lengthy sessions
[@wu2025longmemeval]. BFCL evaluates tool and function calling, including
multi-turn and multi-step settings [@patil2025bfcl]. These datasets were not
designed specifically for context bloat, which is useful here: their natural
agent traces can be annotated independently of the heuristic detector.

The thesis responds with a framework-independent schema exercised through two
controlled execution paths, client-side request capture, separated evidence
namespaces, source-level metrics, a controlled perturbation benchmark,
independently annotated natural traces, and paired counterfactual and
compression analyses. The contribution is not a claim to solve context
management in general. It is a reproducible engineering and empirical
foundation for asking where suspected bloat appears, whether independent
judges agree, how much it contributes, and what is lost when it is removed.
