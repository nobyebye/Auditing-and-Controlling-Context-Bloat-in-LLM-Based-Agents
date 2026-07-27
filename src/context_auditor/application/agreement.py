"""Agreement statistics for independent context-segment annotations."""

from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Iterable


VALID_DECISIONS = frozenset({"keep", "remove", "uncertain"})


def annotation_agreement(
    reviewer_a: Iterable[dict[str, str]],
    reviewer_b: Iterable[dict[str, str]],
) -> dict:
    left = keyed_complete_rows(reviewer_a)
    right = keyed_complete_rows(reviewer_b)
    shared = sorted(left.keys() & right.keys())
    if not shared:
        raise ValueError("The reviewer files contain no shared completed annotations")
    pairs = [(left[key]["decision"], right[key]["decision"]) for key in shared]
    observed = sum(a == b for a, b in pairs) / len(pairs)
    pooled = Counter(value for pair in pairs for value in pair)
    total = sum(pooled.values())
    probabilities = [count / total for count in pooled.values()]
    kappa_chance = sum(probability**2 for probability in probabilities)
    kappa = chance_corrected(observed, kappa_chance)
    category_count = max(2, len(pooled))
    ac1_chance = sum(
        probability * (1.0 - probability) for probability in probabilities
    ) / (category_count - 1)
    reason_pairs = [
        (primary_reason(left[key]), primary_reason(right[key])) for key in shared
    ]
    return {
        "shared_annotation_count": len(shared),
        "percent_agreement": observed,
        "cohen_kappa": kappa,
        "gwet_ac1": chance_corrected(observed, ac1_chance),
        "krippendorff_alpha_nominal": nominal_alpha(pairs),
        "reason_krippendorff_alpha_nominal": nominal_alpha(reason_pairs),
        "decision_counts": dict(sorted(pooled.items())),
    }


def keyed_complete_rows(rows: Iterable[dict[str, str]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        key = row.get("segment_key", "").strip()
        decision = row.get("decision", "").strip().lower()
        if not key or not decision:
            continue
        if decision not in VALID_DECISIONS:
            raise ValueError(f"Invalid annotation decision for {key}: {decision}")
        if key in result:
            raise ValueError(f"Duplicate annotation row: {key}")
        result[key] = {**row, "decision": decision}
    return result


def primary_reason(row: dict[str, str]) -> str:
    reasons = [
        item.strip()
        for item in row.get("reasons", "").split(";")
        if item.strip()
    ]
    return reasons[0] if reasons else "none"


def chance_corrected(observed: float, chance: float) -> float:
    return (observed - chance) / (1.0 - chance) if chance < 1.0 else 1.0


def nominal_alpha(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    observed_disagreement = mean(float(left != right) for left, right in pairs)
    pooled = Counter(value for pair in pairs for value in pair)
    total = sum(pooled.values())
    expected_disagreement = 1.0 - sum(
        (count / total) ** 2 for count in pooled.values()
    )
    if expected_disagreement == 0:
        return 1.0
    return 1.0 - observed_disagreement / expected_disagreement
