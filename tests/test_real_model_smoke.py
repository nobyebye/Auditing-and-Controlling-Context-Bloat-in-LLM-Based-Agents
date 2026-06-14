from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from context_auditor.cli import build_parser
from context_auditor.io import load_jsonl
from experiments.real_model_smoke import run_real_model_smoke


class RealModelSmokeTests(unittest.TestCase):
    def test_smoke_runner_writes_trace_and_response_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trace_path = root / "smoke.jsonl"
            report_path = root / "smoke_report.json"

            run_real_model_smoke(
                trace_path=trace_path,
                report_path=report_path,
                provider_name="mock",
                model="mock-smoke",
                prompt="Say hello from the smoke test.",
            )

            traces = load_jsonl(trace_path)
            self.assertEqual(len(traces), 1)
            self.assertEqual(traces[0].framework, "real-model-smoke")
            self.assertEqual(traces[0].provider, "mock")
            self.assertEqual(traces[0].model, "mock-smoke")
            self.assertFalse(traces[0].task_output)

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["provider"], "mock")
            self.assertEqual(report["model"], "mock-smoke")
            self.assertGreater(report["response_char_count"], 0)
            self.assertIn("mock response", report["response_preview"])

    def test_cli_exposes_real_model_smoke_command(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "run-real-model-smoke",
                "--provider",
                "deepseek",
                "--model",
                "deepseek-v4-flash",
                "--trace-out",
                "traces/deepseek_smoke.jsonl",
                "--report-out",
                "results/deepseek_smoke_report.json",
            ]
        )
        self.assertEqual(args.provider, "deepseek")
        self.assertEqual(args.model, "deepseek-v4-flash")
        self.assertTrue(callable(args.func))

    def test_cli_exposes_real_model_smoke_config_option(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["run-real-model-smoke", "--config", "configs/deepseek_smoke.json"])
        self.assertEqual(args.config, "configs/deepseek_smoke.json")
        self.assertTrue(callable(args.func))


if __name__ == "__main__":
    unittest.main()
