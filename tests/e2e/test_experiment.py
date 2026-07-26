import json
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from context_auditor.experiments import RunExperiment, load_experiment_config


class ExperimentE2ETests(unittest.TestCase):
    def setUp(self):
        self.project = Path(__file__).resolve().parents[2]

    def test_config_loads_versioned_dataset(self):
        config = load_experiment_config(
            self.project / "configs" / "experiments" / "pilot_custom_react_v1.json"
        )
        self.assertEqual(config.dataset_version, "v1")
        self.assertEqual(config.privacy_mode.value, "redacted")

    def test_invalid_config_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_experiment_config(path)

    def test_custom_pilot_builds_named_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = prepare_project(Path(temporary), self.project)
            config = load_experiment_config(
                root / "configs" / "experiments" / "pilot_custom_react_v1.json"
            )
            run = RunExperiment(root).execute(config)
            manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
            summary = json.loads((run / "reports" / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(summary["trace_count"], 108)
            self.assertTrue((run / "metrics" / "tasks.csv").is_file())

    def test_default_trace_is_redacted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = prepare_project(Path(temporary), self.project)
            config = load_experiment_config(
                root / "configs" / "experiments" / "pilot_custom_react_v1.json"
            )
            run = RunExperiment(root).execute(config)
            trace_text = (run / "traces" / "invocations.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("Authorization:", trace_text)
            self.assertNotIn("DEEPSEEK_API_KEY", trace_text)

    def test_controlled_runner_rejects_mislabeled_real_provider(self):
        config = load_experiment_config(
            self.project / "configs" / "experiments" / "pilot_custom_react_v1.json"
        )
        with self.assertRaises(ValueError):
            RunExperiment(self.project).execute(replace(config, provider="deepseek"))


def prepare_project(destination: Path, source: Path) -> Path:
    shutil.copytree(source / "data", destination / "data")
    shutil.copytree(source / "configs", destination / "configs")
    return destination


if __name__ == "__main__":
    unittest.main()
