# Context Bloat Auditor Architecture

## Design Goals

The v1 architecture keeps research text, controlled data, generated evidence,
and production code in separate ownership boundaries. Every experiment must be
named, reproducible, non-overwriting, and traceable to source inputs.

## Dependency Rule

```text
domain <- application <- adapters
                 ^          |
                 |          |
                ports <-----+
```

- `domain` contains immutable models and policies and imports no project layer.
- `application` implements use cases and depends only on domain and ports.
- `ports` defines infrastructure contracts.
- `adapters` implement framework, provider, storage, clock, tokenizer and ID
  contracts.
- `experiments` composes use cases and adapters.
- `cli` is the outermost entry point.

Architecture tests reject domain-to-infrastructure and
application-to-provider/framework dependencies.

## Text Lifecycle

1. An agent or framework constructs model-visible `Message` objects.
2. `CaptureContext` labels and segments the messages before persistence.
3. Metrics use the original in-memory text.
4. The selected privacy policy transforms persisted message and segment text.
5. Raw and normalized SHA-256 values preserve identity and duplicate evidence.
6. The JSONL repository appends the immutable `AuditTrace`.
7. Analysis and reporting read traces and create named derived artifacts.

## Run Lifecycle

`RunRegistry` creates a unique run directory and a `running` manifest before
the experiment starts. Existing directories cause an immediate failure.

Successful runs write metrics, reports and figures, hash every output, and set
the manifest to `completed`. Exceptions produce a `failed` manifest containing
the exception type without exposing credentials.

## Version Boundaries

- Project version identifies the executable artifact.
- Trace schema version identifies serialized trace compatibility.
- Config schema version identifies experiment input compatibility.
- Dataset versions are immutable directories.
- Git commit, config hash and dataset hash bind a run to its exact inputs.

The v0 implementation is intentionally absent from the v1 working tree. It is
recoverable from the `v0.10.0-pilot-archive` tag.
