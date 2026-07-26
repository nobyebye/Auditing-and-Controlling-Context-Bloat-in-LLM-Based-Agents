# Data Dictionary

## Message

| Field | Meaning |
|---|---|
| `role` | Model API role such as system, user, assistant, or tool. |
| `content` | Persisted content after the selected privacy policy. |
| `name` | Optional provider or tool message name. |
| `metadata` | Explicit provenance and framework metadata. |

## TextSegment

| Field | Meaning |
|---|---|
| `segment_id` | Stable invocation-local segment identifier. |
| `parent_message_id` | Message from which the segment was derived. |
| `message_index` / `ordinal` | Original message and segment order. |
| `source_type` | System, user, framework, retrieval, memory, tool, generated trace, or other. |
| `text` | Full, redacted, or hash-only persisted representation. |
| `char_count` / `token_count` | Counts calculated before privacy transformation. |
| `content_hash` | SHA-256 of exact original text. |
| `normalized_hash` | SHA-256 after case folding and whitespace normalization. |
| `privacy_mode` | Persistence policy used for this segment. |

## AuditTrace

An invocation trace binds messages and segments to experiment, run, task,
framework, provider, model, dataset version, configuration, repetition, seed,
invocation index and timestamp. It also stores aggregate metrics, risk flags,
mitigation decisions, task evaluation, provider usage and latency.

## RunManifest

The manifest is the reproducibility index. It records code, environment,
configuration, data, model, lifecycle status, all output paths and hashes, token
usage, and a sanitized failure reason.
