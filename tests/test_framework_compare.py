from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from context_auditor.framework_compare import compare_framework_summaries, write_framework_comparison_csv


class FrameworkCompareTests(unittest.TestCase):
    def test_compares_matching_configurations_between_two_frameworks(self) -> None:
        custom_summary = {
            "frameworks": ["custom-react"],
            "trace_count": 2,
            "by_configuration": {
                "baseline": {
                    "invocations": 2,
                    "mean_total_tokens": 10.0,
                    "mean_redundancy_ratio": 0.1,
                    "task_success_rate": 1.0,
                }
            },
        }
        langchain_summary = {
            "frameworks": ["langchain"],
            "trace_count": 2,
            "by_configuration": {
                "baseline": {
                    "invocations": 2,
                    "mean_total_tokens": 12.0,
                    "mean_redundancy_ratio": 0.2,
                    "task_success_rate": 0.5,
                }
            },
        }

        comparison = compare_framework_summaries(
            {
                "custom-react": custom_summary,
                "langchain": langchain_summary,
            }
        )

        self.assertEqual(comparison["frameworks"], ["custom-react", "langchain"])
        self.assertEqual(comparison["configuration_count"], 1)
        self.assertEqual(comparison["rows"][0]["configuration"], "baseline")
        self.assertEqual(comparison["rows"][0]["baseline_framework"], "custom-react")
        self.assertEqual(comparison["rows"][0]["comparison_framework"], "langchain")
        self.assertEqual(comparison["rows"][0]["mean_total_tokens_delta"], 2.0)
        self.assertEqual(comparison["rows"][0]["mean_redundancy_ratio_delta"], 0.1)
        self.assertEqual(comparison["rows"][0]["task_success_rate_delta"], -0.5)

    def test_writes_framework_comparison_csv(self) -> None:
        comparison = {
            "rows": [
                {
                    "configuration": "baseline",
                    "baseline_framework": "custom-react",
                    "comparison_framework": "langchain",
                    "baseline_mean_total_tokens": 10.0,
                    "comparison_mean_total_tokens": 12.0,
                    "mean_total_tokens_delta": 2.0,
                    "baseline_mean_redundancy_ratio": 0.1,
                    "comparison_mean_redundancy_ratio": 0.2,
                    "mean_redundancy_ratio_delta": 0.1,
                    "baseline_task_success_rate": 1.0,
                    "comparison_task_success_rate": 0.5,
                    "task_success_rate_delta": -0.5,
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "framework_comparison.csv"
            write_framework_comparison_csv(comparison, path)

            with path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["configuration"], "baseline")
            self.assertEqual(rows[0]["mean_total_tokens_delta"], "2.0")


if __name__ == "__main__":
    unittest.main()
