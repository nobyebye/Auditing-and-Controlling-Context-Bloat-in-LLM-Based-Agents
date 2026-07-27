# Context Segment Annotation Codebook v1.2

Annotate whether each segment can be removed from the model-visible request
without removing information reasonably needed to complete the stated task.
Do not predict whether the current model happened to use the segment. Judge the
information available before seeing the answer.

## Decision

- `keep`: the segment contains task-relevant evidence, an operative constraint,
  a required tool observation, or information whose removal could reasonably
  change a correct answer.
- `remove`: the segment appears avoidable for this task.
- `uncertain`: the available context is insufficient to make a defensible
  keep/remove judgement.

## Remove reasons

- `exact_duplicate`: the same information is repeated verbatim.
- `near_duplicate`: substantially the same information is repeated with minor
  wording differences.
- `low_query_relevance`: the information does not contribute to the stated
  task.
- `stale_context`: the information has been superseded, conflicts with newer
  context, or is no longer applicable.
- `verbose_tool_output`: a tool result contains task-irrelevant diagnostics or
  detail that can be removed while preserving its useful result.
- `other`: avoidable content not covered above; explain it in notes.

Multiple reasons are separated with semicolons. A `remove` decision requires at
least one reason. A `keep` decision normally has no remove reason.

## Confidence

Use an integer from 1 to 5, where 1 is a weak judgement and 5 is a judgement
that would be unlikely to change after discussion.

## Blinding and adjudication

Annotators must not open `answer_key.csv` and must not inspect detector outputs,
conditions or model answers while performing segment annotation. Both
annotators complete the full test set independently. Agreement is calculated
before discussion. Disagreements are then resolved in `adjudication.csv`;
original reviewer files are never overwritten.
