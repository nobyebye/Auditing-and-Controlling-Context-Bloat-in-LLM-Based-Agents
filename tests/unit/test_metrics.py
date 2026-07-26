import unittest

from context_auditor.analytics.metrics import (
    compute_metrics,
    jaccard_similarity,
    query_overlap_ratio,
)
from context_auditor.domain.models import TextSegment


def segment(index: int, text: str, normalized: str, source: str = "retrieval") -> TextSegment:
    return TextSegment(
        segment_id=f"s{index}",
        parent_message_id=f"m{index}",
        message_index=index,
        ordinal=0,
        role="system",
        source_type=source,
        text=text,
        char_count=len(text),
        token_count=len(text.split()),
        content_hash=str(index),
        normalized_hash=normalized,
        privacy_mode="full",
    )


class MetricsTests(unittest.TestCase):
    def test_jaccard_identical(self):
        self.assertEqual(jaccard_similarity("a b", "a b"), 1.0)

    def test_jaccard_disjoint(self):
        self.assertEqual(jaccard_similarity("a", "b"), 0.0)

    def test_query_overlap(self):
        self.assertEqual(query_overlap_ratio("remote work", "remote policy"), 0.5)

    def test_empty_query_overlap(self):
        self.assertEqual(query_overlap_ratio("text", ""), 0.0)

    def test_counts_exact_duplicate(self):
        metrics = compute_metrics([segment(0, "same text", "x"), segment(1, "same text", "x")])
        self.assertEqual(metrics["duplicate_segment_count"], 1)
        self.assertEqual(metrics["redundant_tokens"], 2)

    def test_source_ratios_sum_to_one(self):
        metrics = compute_metrics(
            [segment(0, "one", "a"), segment(1, "two", "b", source="memory")]
        )
        self.assertAlmostEqual(sum(metrics["source_ratios"].values()), 1.0)

    def test_unique_information_without_duplicates(self):
        metrics = compute_metrics([segment(0, "one", "a"), segment(1, "two", "b")])
        self.assertEqual(metrics["unique_information_ratio"], 1.0)

    def test_empty_metrics_are_defined(self):
        metrics = compute_metrics([])
        self.assertEqual(metrics["total_tokens"], 0)
        self.assertEqual(metrics["redundancy_ratio"], 0.0)


if __name__ == "__main__":
    unittest.main()
