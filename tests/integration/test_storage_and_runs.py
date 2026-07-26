import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from context_auditor.adapters.common import validate_run_id
from context_auditor.adapters.storage import FileDatasetRepository, JsonlTraceRepository, RunRegistry
from context_auditor.adapters.storage.serialization import write_json_atomic
from context_auditor.domain.enums import RunStatus


VALID_RUN_ID = "20260726T120000Z__custom-react__mock-llm__v1__05bd18f"


class StorageAndRunTests(unittest.TestCase):
    def test_valid_run_id(self):
        validate_run_id(VALID_RUN_ID)

    def test_invalid_run_id(self):
        with self.assertRaises(ValueError):
            validate_run_id("run 1")

    def test_run_registry_creates_fixed_layout(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths, manifest = create_run(Path(temporary))
            self.assertTrue(paths.traces.parent.is_dir())
            self.assertEqual(manifest.status, RunStatus.RUNNING)

    def test_run_collision_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            create_run(Path(temporary))
            with self.assertRaises(FileExistsError):
                create_run(Path(temporary))

    def test_completion_hashes_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths, manifest = create_run(root)
            paths.log.write_text("complete\n", encoding="utf-8")
            completed = RunRegistry(root).complete(paths, manifest)
            self.assertIn("logs/run.log", completed.output_hashes)

    def test_failure_records_reason(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths, manifest = create_run(root)
            failed = RunRegistry(root).fail(paths, manifest, "failure")
            self.assertEqual(failed.status, RunStatus.FAILED)
            self.assertEqual(failed.failure_reason, "failure")

    def test_atomic_json_is_utf8(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "value.json"
            write_json_atomic(path, {"title": "硕士论文"})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["title"], "硕士论文")

    def test_empty_jsonl_repository_iterates_empty(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = JsonlTraceRepository(Path(temporary) / "missing.jsonl")
            self.assertEqual(list(repository.iter_traces()), [])

    def test_dataset_hash_is_stable(self):
        project = Path(__file__).resolve().parents[2]
        repository = FileDatasetRepository(project / "data")
        first = repository.content_hash("controlled_synthetic", "v1")
        second = repository.content_hash("controlled_synthetic", "v1")
        self.assertEqual(first, second)


def create_run(root: Path):
    config = root / "config.json"
    config.write_text("{}", encoding="utf-8")
    return RunRegistry(root).create(
        experiment_id="test",
        framework="custom-react",
        provider="mock",
        model="mock-llm",
        config_path=config,
        config_hash="abc",
        dataset_name="controlled",
        dataset_version="v1",
        dataset_hash="def",
        seed=42,
        repetition_id=0,
        run_id=VALID_RUN_ID,
    )


if __name__ == "__main__":
    unittest.main()
