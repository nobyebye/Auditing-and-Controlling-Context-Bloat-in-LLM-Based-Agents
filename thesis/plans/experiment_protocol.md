# Formal Context Bloat Experiment Protocol

## Scope

This protocol evaluates detection, localization, measurement, and mitigation of
context bloat in LLM-based agents. Runtime tracing and provenance labeling are
the measurement infrastructure; context bloat is the primary research problem.

The primary hypothesis analysis uses only the held-out `test` split. Calibration
tasks are used to freeze thresholds and are never included in primary RQ
evidence. Cross-source stress cases are labeled `analysis_cohort=stress` and are
reported separately.

## Frozen Dataset

Dataset: `data/datasets/context_bloat_benchmark/v1/`

- 36 tasks in total.
- 6 calibration tasks.
- 30 held-out test tasks.
- 12 retrieval QA, 12 memory-turn, and 12 multi-step tool tasks.
- Four ground-truth labels: `exact_duplicate`, `near_duplicate`,
  `low_query_relevance`, and `verbose_tool_output`.
- Six predeclared test tasks are reused for the separate cross-source stress
  analysis.

Any content change requires a new dataset version. The run manifest records the
dataset content hash.

## Implementations And Model

- `custom-react`: controlled ReAct-style loop using the shared provider port.
- `langchain`: actual `BaseChatModel.invoke()` execution with callback capture.
- Provider: DeepSeek.
- Model identifier: `deepseek-v4-flash`.
- Temperature: `0.0`.
- Maximum output tokens: `256`.
- Repetitions: `3`.
- Privacy mode: `redacted`.

Every real-provider formal run requires a clean Git worktree. The runner refuses
to start otherwise, ensuring that the manifest commit identifies the executed
code.

## Primary Conditions

Each workflow has six conditions:

1. `baseline`
2. `sufficient`
3. `exact_bloat`
4. `source_specific_bloat`
5. `combined_bloat`
6. `mitigated`

Primary matrix:

```text
30 tasks x 6 conditions x 3 repetitions x 2 frameworks
= 1080 final task executions
```

Tool tasks use one planning invocation and one final invocation. The resulting
primary trace count is 1380, while only the 1080 final invocations are used for
task-success and measurement evaluation.

## Cross-Source Stress Cohort

Six fixed held-out tasks receive retrieval, memory, and tool context together.
The conditions are `sufficient`, `combined_bloat`, and `mitigated`.

```text
6 tasks x 3 conditions x 3 repetitions x 2 frameworks
= 108 final task executions
= 216 model invocations
```

Stress traces are packaged with the study but excluded from primary RQ
inference.

## Metrics And Inference

- Exact and near redundancy ratios.
- Ground-truth and detected bloat-token ratios.
- Context growth rate.
- Source contribution and source-specific bloat ratio.
- Detection precision, recall, macro-F1, and localization accuracy.
- Spearman correlation between measured and ground-truth bloat.
- Input/output tokens, latency, and estimated API cost.
- Rule-based task success.
- Paired mitigation token reduction and task-success difference.

Confidence intervals use 10,000 deterministic bootstrap samples. The
mitigation analysis clusters repetitions by `framework x task`, producing 60
independent task clusters from 180 paired observations. RQ4 uses a frozen
non-inferiority margin of `-5%` for task-success difference.

## Human Review

The final bundle exports:

- `reviewer_a.csv`: 72 condition-blind outputs.
- `reviewer_b.csv`: a 36-output reliability subset.
- `answer_key.csv`: hidden condition, framework, reference, and automatic score.
- `annotation_manifest.json`: source bundle hash and deterministic sample seed.

Reviewers must not receive `answer_key.csv` until both review forms are frozen.
Human labels are not yet part of RQ evidence until the completed forms are
validated and inter-rater agreement is calculated.

## Reproducibility Commands

Validate the dataset:

```powershell
python -m context_auditor.cli validate-dataset --project-root .
```

Run primary real-provider experiments:

```powershell
python -m context_auditor.cli run-formal-suite `
  --custom-config configs/experiments/formal_custom_react_deepseek_v1.json `
  --langchain-config configs/experiments/formal_langchain_deepseek_v1.json `
  --project-root . `
  --confirm-real-cost
```

Run cross-source stress experiments:

```powershell
python -m context_auditor.cli run-formal-suite `
  --custom-config configs/experiments/formal_stress_custom_react_deepseek_v1.json `
  --langchain-config configs/experiments/formal_stress_langchain_deepseek_v1.json `
  --project-root . `
  --confirm-real-cost
```

Export and validate the study using the four completed run directories:

```powershell
python -m context_auditor.cli export-study `
  --project-root . `
  --run <primary-custom-run> `
  --run <primary-langchain-run> `
  --run <stress-custom-run> `
  --run <stress-langchain-run> `
  --output runs/studies/formal-deepseek-v1-final.zip

python -m context_auditor.cli validate-study `
  --bundle runs/studies/formal-deepseek-v1-final.zip
```

Export blind review forms:

```powershell
python -m context_auditor.cli export-annotations `
  --bundle runs/studies/formal-deepseek-v1-final.zip `
  --output runs/studies/formal-deepseek-v1-final-annotations `
  --seed 20260726
```

## Acceptance Checks

- Four selected component manifests have status `completed`.
- Every component artifact matches its manifest SHA-256.
- Study schema is `1.1.0`.
- Bundle contains 1596 traces: 1380 primary and 216 stress.
- Primary measurement sample contains 1080 final invocations.
- Primary inference uses 30 tasks; stress uses six reused tasks separately.
- Bundle records both component execution commits and the analysis commit.
- Reviewer A/B sample counts are 72/36.
