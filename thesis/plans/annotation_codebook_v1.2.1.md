# Context Segment Annotation Codebook v1.2.1

## Annotation question

For each displayed context segment, decide whether the segment should remain in
the model-visible request for the stated task. Judge the information available
before seeing the model answer. Do not guess whether the model happened to use
the segment.

## Decisions

- `keep`: the segment contains task-relevant evidence, an operative constraint,
  a required tool observation, or information whose removal could reasonably
  alter a correct answer.
- `remove`: the segment appears avoidable for this task.
- `uncertain`: the evidence is insufficient for a defensible keep/remove
  judgement.

The human decision concerns perceived relevance or avoidability. It is not a
counterfactual proof that deletion preserves task utility.

## Remove reasons

- `exact_duplicate`: the same information is repeated verbatim.
- `near_duplicate`: substantially the same information is repeated with minor
  wording differences.
- `low_query_relevance`: the information does not contribute to the stated
  task.
- `stale_context`: the information has been superseded, conflicts with newer
  context, or is no longer applicable.
- `verbose_tool_output`: a tool result includes removable diagnostics or detail
  while retaining a useful result elsewhere.
- `other`: avoidable material not covered above; explain it in notes.

Use semicolons for multiple reasons. A `remove` decision requires at least one
reason. A `keep` or `uncertain` decision should normally have no remove reason.

## Confidence

Enter an integer from 1 to 5. `1` indicates a weak judgement; `5` indicates a
judgement unlikely to change after discussion. Confidence does not replace the
decision and is not used to silently discard a label.

## Segment boundary rule

Evaluate exactly the displayed segment. Do not merge it with another segment
or split it into smaller units. Message order and segment order must remain
unchanged. Similar-looking segments from the two frameworks are judged
independently; reviewers must not align them.

## Blinding

Reviewers must not inspect `answer_key.csv`, source labels, framework identity,
detector flags, conditions, model outputs, or automatic scores. Questions about
the codebook are recorded during calibration. Held-out test labels must not be
used to revise detector thresholds.

## Work sessions

Each workbook contains at most ten contexts for Study B. Complete no more than
two blocks per session, then take a break of at least ten minutes. Enter UTC
start and completion times on the `Session` sheet. Reviewers receive different
block orders, while segment order inside a context remains fixed.

## Adjudication

Both reviewers complete all held-out contexts independently. Raw agreement is
calculated before discussion. Discussion then resolves disagreements in a
separate adjudication file. Original reviewer files are never overwritten.
When no consensus is possible, retain `uncertain`.

## Analysis treatment of uncertain

- Primary analysis: exclude uncertain segments.
- Sensitivity A: treat uncertain as keep/non-bloat.
- Sensitivity B: treat uncertain as remove/bloat.
