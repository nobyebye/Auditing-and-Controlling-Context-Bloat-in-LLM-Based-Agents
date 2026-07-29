# Prospective Calibration Implementation Correction v1.2.1

## Scope and timing

This correction was prepared after the first Custom ReAct calibration run
encountered four HTTP 400 responses and before any LangChain calibration
request, calibration annotation, threshold selection, held-out Study B
request, or Study C request.

It supplements:

- Initial OSF registration: https://osf.io/ue4vw/overview
- Calibration-method clarification: https://osf.io/a75wd/overview

The registered research questions, datasets, held-out split, annotation
procedure, threshold-selection method, outcomes, evidence hierarchy, and
500-request budget are unchanged.

## Observed deviation

The Custom ReAct calibration run
`20260729T122142Z__custom-react__deepseek-v4-flash__v1__e47e29cc`
dispatched 16 provider requests. Twelve completed and four second-invocation
tool requests received HTTP 400 responses. No automatic or manual retry was
made. The four failed requests remain in the append-only call ledger and count
toward the 500-request limit.

The failures occurred for:

- `bfcl-multi_turn_base_80`
- `bfcl-multi_turn_base_57`
- `bfcl-multi_turn_base_138`
- `bfcl-multi_turn_base_157`

The immutable, content-free event summary is archived as
`calibration_deviation_summary_v1.2.1.json`.

## Root cause

The first provider response contained one or more tool calls. The follow-up
context preserved the assistant text and tool observations, but the provider
serializer omitted:

1. the assistant message's structured `tool_calls`; and
2. each tool message's required `tool_call_id`.

The malformed follow-up payload therefore did not satisfy the registered
provider's OpenAI-compatible tool-call message contract. This was an
implementation defect, not an observed task-performance failure.

## Prospective correction

Before any additional real provider request, the implementation is changed to:

- represent `tool_calls` and `tool_call_id` explicitly in the immutable
  message model;
- preserve these fields in Custom ReAct and LangChain conversions;
- serialize assistant tool calls and matching tool-result IDs in the final
  client-side request;
- reject a tool message without a `tool_call_id` before dispatch;
- preserve the fields through trace JSONL round trips and privacy processing;
- add unit, integration, and mock end-to-end regression tests.

The already dispatched requests and traces are not edited or replaced. The
four HTTP 400 calls are not eligible for the registered manual-retry mechanism,
which is restricted to timeouts, HTTP 429, and HTTP 5xx responses.

## Continuation rule

Calibration remains blocked until this correction package is:

1. committed and published in a GitHub Release;
2. registered immediately and publicly on OSF;
3. linked to the calibration-method clarification registration; and
4. verified locally by URL, timestamp, package hash, release tag, release
   commit, and frozen runtime-file hashes.

After verification, only the unattempted LangChain calibration cells may be
run. The original Custom ReAct run is read-only and will not be replayed.
Calibration therefore remains capped at 32 primary provider requests: 16
already dispatched Custom ReAct requests and at most 16 unattempted LangChain
requests.

The four affected final tool contexts may be retained for context annotation
because the context representation exists, but their provider execution status
must remain `failed`. Any analysis that requires a successfully accepted
provider request or generated final answer must exclude them under an explicit
failure rule and report the count.

This prospective correction repairs provider-message serialization only. It
does not introduce calibration results, inspect held-out data, alter detector
thresholds, or modify the registered primary Study B/C analyses.
