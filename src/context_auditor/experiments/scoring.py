"""Deterministic task scoring used by the formal study."""

from __future__ import annotations

import math
import re
import string

from context_auditor.domain.models import ScoringResult

WORD_RE = re.compile(r"\w+", re.UNICODE)
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def score_response(task: dict, output: str) -> ScoringResult:
    scoring = task.get("scoring", {"type": "contains"})
    method = str(scoring.get("type", "contains"))
    expected = str(task["expected_answer"])
    aliases = [expected, *[str(item) for item in task.get("answer_aliases", [])]]
    normalized_output = normalize(output)
    normalized_expected = normalize(expected)

    if method == "numeric":
        tolerance = float(scoring.get("tolerance", 1e-6))
        observed = last_number(output)
        target = float(expected)
        success = observed is not None and math.isclose(
            observed, target, rel_tol=0.0, abs_tol=tolerance
        )
        return ScoringResult(
            success=success,
            score=1.0 if success else 0.0,
            method=method,
            normalized_output=normalized_output,
            normalized_expected=normalized_expected,
            details={"observed": observed, "tolerance": tolerance},
        )

    if method == "exact":
        success = any(normalized_output == normalize(alias) for alias in aliases)
        score = 1.0 if success else 0.0
    elif method == "hotpotqa_f1":
        normalized_output = normalize_hotpot(output)
        normalized_expected = normalize_hotpot(expected)
        score = max(
            token_f1(normalized_output, normalize_hotpot(alias))
            for alias in aliases
        )
        success = score >= float(scoring.get("minimum_f1", 0.8))
    elif method == "token_f1":
        score = max(token_f1(normalized_output, normalize(alias)) for alias in aliases)
        success = score >= float(scoring.get("minimum_f1", 0.8))
    else:
        success = any(normalize(alias) in normalized_output for alias in aliases)
        score = 1.0 if success else 0.0
        method = "contains"

    return ScoringResult(
        success=success,
        score=score,
        method=method,
        normalized_output=normalized_output,
        normalized_expected=normalized_expected,
    )


def normalize(text: str) -> str:
    return " ".join(WORD_RE.findall(text.casefold()))


def normalize_hotpot(text: str) -> str:
    lowered = text.casefold()
    without_punctuation = "".join(
        character for character in lowered if character not in string.punctuation
    )
    without_articles = re.sub(r"\b(a|an|the)\b", " ", without_punctuation)
    return " ".join(without_articles.split())


def last_number(text: str) -> float | None:
    matches = NUMBER_RE.findall(text.replace(",", ""))
    return float(matches[-1]) if matches else None


def token_f1(left: str, right: str) -> float:
    left_tokens = left.split()
    right_tokens = right.split()
    if not left_tokens or not right_tokens:
        return float(left_tokens == right_tokens)
    common = sum(min(left_tokens.count(token), right_tokens.count(token)) for token in set(left_tokens))
    precision = common / len(left_tokens)
    recall = common / len(right_tokens)
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0
