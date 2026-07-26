"""Validated, browser-consumable study bundle export."""

from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable

from context_auditor.adapters.common import UtcClock
from context_auditor.adapters.storage import JsonlTraceRepository
from context_auditor.adapters.storage.runs import file_hash
from context_auditor.adapters.storage.serialization import dumps, write_json_atomic
from context_auditor.application.analysis import AnalyzeBloat
from context_auditor.application.reporting import BuildReport
from context_auditor.domain.enums import RunStatus

REQUIRED_BUNDLE_FILES = {
    "study_manifest.json",
    "checksums.json",
    "reports/summary.json",
    "reports/rq_evidence.json",
    "configs/rq_rules.json",
    "traces/invocations.jsonl",
}


class ExportStudyBundle:
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root)

    def execute(
        self,
        run_paths: Iterable[str | Path],
        output: str | Path,
        *,
        public_demo: bool = False,
    ) -> Path:
        selected = [Path(path).resolve() for path in run_paths]
        if not selected:
            raise ValueError("At least one component run is required")
        manifests = [validate_component_run(path) for path in selected]
        privacy_modes = {
            trace.privacy_mode
            for path in selected
            for trace in JsonlTraceRepository(
                path / "traces" / "invocations.jsonl"
            ).iter_traces()
        }
        dataset_names = {manifest["dataset_name"] for manifest in manifests}
        if public_demo and "full" in privacy_modes:
            raise ValueError("Public demo bundles cannot contain full-text traces")
        if public_demo and not dataset_names <= {
            "controlled_synthetic",
            "context_bloat_benchmark",
        }:
            raise ValueError("Public demo bundles require an approved controlled dataset")

        destination = Path(output)
        if destination.exists():
            raise FileExistsError(f"Study bundle already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="context-auditor-study-") as temporary:
            root = Path(temporary)
            traces = [
                trace
                for path in selected
                for trace in JsonlTraceRepository(
                    path / "traces" / "invocations.jsonl"
                ).iter_traces()
            ]
            summary = AnalyzeBloat().execute(traces)
            rules = json.loads(
                (
                    self.project_root
                    / "configs"
                    / "conclusions"
                    / "rq_rules_v1.json"
                ).read_text(encoding="utf-8")
            )
            BuildReport().execute(
                traces,
                summary,
                invocation_csv=root / "reports" / "tables" / "invocations.csv",
                task_csv=root / "reports" / "tables" / "tasks.csv",
                summary_json=root / "reports" / "summary.json",
                rq_evidence_json=root / "reports" / "rq_evidence.json",
                rq_rules=rules,
                tables_dir=root / "reports" / "tables",
                figures_dir=root / "reports" / "figures",
            )
            trace_path = root / "traces" / "invocations.jsonl"
            trace_path.parent.mkdir(parents=True, exist_ok=True)
            trace_path.write_text(
                "".join(dumps(trace) + "\n" for trace in traces),
                encoding="utf-8",
            )
            write_json_atomic(root / "configs" / "rq_rules.json", rules)
            study_manifest = {
                "schema_version": "1.1.0",
                "study_id": destination.stem,
                "created_at": UtcClock().now_iso(),
                "public_demo": public_demo,
                "component_runs": [
                    {
                        "path": path.name,
                        "experiment_id": manifest["experiment_id"],
                        "run_id": manifest["run_id"],
                        "git_commit": manifest["git_commit"],
                        "framework": manifest["framework"],
                        "provider": manifest["provider"],
                        "model": manifest["model"],
                        "manifest_sha256": file_hash(path / "manifest.json"),
                    }
                    for path, manifest in zip(selected, manifests)
                ],
                "frameworks": sorted({item["framework"] for item in manifests}),
                "providers": sorted({item["provider"] for item in manifests}),
                "models": sorted({item["model"] for item in manifests}),
                "datasets": sorted(dataset_names),
                "privacy_modes": sorted(privacy_modes),
                "trace_count": len(traces),
                "task_count": len({trace.task_id for trace in traces}),
            }
            write_json_atomic(root / "study_manifest.json", study_manifest)
            checksums = {
                path.relative_to(root).as_posix(): file_hash(path)
                for path in sorted(root.rglob("*"))
                if path.is_file() and path.name != "checksums.json"
            }
            write_json_atomic(root / "checksums.json", checksums)
            write_deterministic_zip(root, destination)
        validate_study_bundle(destination)
        return destination


def validate_component_run(path: Path) -> dict:
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Run manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != RunStatus.COMPLETED.value:
        raise ValueError(f"Component run is not completed: {path}")
    if manifest.get("schema_version") != "1.1.0":
        raise ValueError(f"Component run schema is not 1.1.0: {path}")
    for relative, expected in manifest.get("output_hashes", {}).items():
        artifact = path / relative
        if not artifact.is_file() or file_hash(artifact) != expected:
            raise ValueError(f"Component run artifact hash mismatch: {artifact}")
    return manifest


def validate_study_bundle(path: str | Path) -> dict:
    bundle = Path(path)
    if not bundle.is_file():
        raise FileNotFoundError(f"Study bundle does not exist: {bundle}")
    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        missing = sorted(REQUIRED_BUNDLE_FILES - names)
        if missing:
            raise ValueError("Study bundle is missing: " + ", ".join(missing))
        if any(name.startswith("/") or ".." in Path(name).parts for name in names):
            raise ValueError("Study bundle contains an unsafe path")
        manifest = json.loads(archive.read("study_manifest.json").decode("utf-8"))
        if manifest.get("schema_version") != "1.1.0":
            raise ValueError("Unsupported study bundle schema")
        checksums = json.loads(archive.read("checksums.json").decode("utf-8"))
        for name, expected in checksums.items():
            if name not in names:
                raise ValueError(f"Checksummed bundle file is missing: {name}")
            observed = hashlib.sha256(archive.read(name)).hexdigest()
            if observed != expected:
                raise ValueError(f"Study bundle checksum mismatch: {name}")
        if manifest.get("public_demo") and "full" in manifest.get("privacy_modes", []):
            raise ValueError("Public demo bundle contains full-text traces")
        return {
            "valid": True,
            "schema_version": manifest["schema_version"],
            "study_id": manifest["study_id"],
            "trace_count": manifest["trace_count"],
            "task_count": manifest["task_count"],
            "public_demo": manifest["public_demo"],
        }


def write_deterministic_zip(root: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            info = zipfile.ZipInfo(path.relative_to(root).as_posix())
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
