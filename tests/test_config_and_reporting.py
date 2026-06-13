from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from context_auditor.reporting import write_summary_tables, write_svg_bar_charts
from experiments.config import load_experiment_config


class ConfigAndReportingTests(unittest.TestCase):
    def test_load_default_config(self) -> None:
        config = load_experiment_config("configs/pilot.json")
        self.assertEqual(config.experiment_id, "pilot-context-bloat-v0.3")
        self.assertIn("retrieval_qa", config.workflow_configs)
        self.assertEqual(config.workflow_configs["retrieval_qa"][0].configuration, "baseline")

    def test_reporting_writes_tables_and_charts(self) -> None:
        summary = {
            "by_configuration": {
                "baseline": {
                    "invocations": 1,
                    "mean_total_tokens": 10,
                    "mean_total_chars": 50,
                    "mean_redundancy_ratio": 0.0,
                    "mean_unique_information_ratio": 1.0,
                    "duplicate_segment_count": 0,
                    "task_success_rate": 1.0,
                }
            },
            "by_workflow_family": {
                "retrieval_qa": {
                    "invocations": 1,
                    "mean_total_tokens": 10,
                    "mean_total_chars": 50,
                    "mean_redundancy_ratio": 0.0,
                    "mean_unique_information_ratio": 1.0,
                    "duplicate_segment_count": 0,
                    "task_success_rate": 1.0,
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_summary_tables(summary, out / "tables")
            write_svg_bar_charts(summary, out / "charts")
            self.assertTrue((out / "tables" / "by_configuration.csv").exists())
            self.assertTrue((out / "charts" / "tokens_by_configuration.svg").exists())


if __name__ == "__main__":
    unittest.main()
