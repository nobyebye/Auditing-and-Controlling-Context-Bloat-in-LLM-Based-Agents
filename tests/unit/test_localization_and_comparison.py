import unittest

from context_auditor.application.comparison import CompareFrameworks
from context_auditor.application.localization import LocalizeBloat
from context_auditor.domain.models import AuditTrace, TextSegment


class LocalizationTests(unittest.TestCase):
    def test_localizes_exact_duplicate(self):
        trace = make_trace(
            (
                make_segment("s1", "same", "hash"),
                make_segment("s2", "same", "hash"),
            )
        )
        findings = LocalizeBloat().execute(trace, "same")
        self.assertIn("exact_duplicate", [finding.label for finding in findings])

    def test_localizes_irrelevant_retrieval(self):
        trace = make_trace((make_segment("s1", "hardware repair", "hash"),))
        findings = LocalizeBloat().execute(trace, "remote policy")
        self.assertIn("low_query_relevance", [finding.label for finding in findings])


class ComparisonTests(unittest.TestCase):
    def test_compares_aligned_configurations(self):
        baseline = summary("custom-react", 10.0, 1.0)
        comparison = summary("langchain", 12.0, 0.5)
        result = CompareFrameworks().execute(baseline, comparison)
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["rows"][0]["mean_total_tokens_delta"], 2.0)
        self.assertEqual(result["rows"][0]["task_success_rate_delta"], -0.5)


def make_segment(segment_id: str, text: str, normalized: str) -> TextSegment:
    return TextSegment(
        segment_id=segment_id,
        parent_message_id="m1",
        message_index=0,
        ordinal=0,
        role="system",
        source_type="retrieval",
        text=text,
        char_count=len(text),
        token_count=2,
        content_hash=normalized,
        normalized_hash=normalized,
        privacy_mode="full",
    )


def make_trace(segments: tuple[TextSegment, ...]) -> AuditTrace:
    return AuditTrace(
        schema_version="1.0.0",
        trace_id="trace",
        timestamp="2026-01-01T00:00:00+00:00",
        experiment_id="test",
        run_id="run",
        task_id="task",
        framework="custom-react",
        provider="mock",
        model="mock",
        configuration="test",
        workflow_family="retrieval_qa",
        dataset_name="controlled",
        dataset_version="v1",
        repetition_id=0,
        seed=42,
        invocation_index=0,
        config_hash="abc",
        privacy_mode="full",
        messages=(),
        segments=segments,
        metrics={},
    )


def summary(framework: str, tokens: float, success: float) -> dict:
    return {
        "frameworks": [framework],
        "by_configuration": {
            "baseline": {
                "mean_total_tokens": tokens,
                "mean_redundancy_ratio": 0.1,
                "task_success_rate": success,
            }
        },
    }


if __name__ == "__main__":
    unittest.main()
