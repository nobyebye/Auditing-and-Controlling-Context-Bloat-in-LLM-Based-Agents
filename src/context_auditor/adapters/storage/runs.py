"""Unique run-directory creation and manifest lifecycle."""

from __future__ import annotations

import hashlib
import importlib.metadata
import platform
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from context_auditor import __version__
from context_auditor.domain.enums import RunStatus
from context_auditor.domain.models import ProviderUsage, RunManifest, SCHEMA_VERSION
from context_auditor.domain.text import redact_text

from ..common import DefaultIdGenerator, UtcClock, validate_run_id
from .serialization import write_json_atomic


@dataclass(frozen=True)
class RunPaths:
    root: Path
    manifest: Path
    log: Path
    traces: Path
    invocation_metrics: Path
    task_metrics: Path
    summary: Path
    rq_evidence: Path
    tables: Path
    figures: Path


class RunRegistry:
    def __init__(self, runs_root: str | Path, clock: UtcClock | None = None) -> None:
        self.runs_root = Path(runs_root)
        self.clock = clock or UtcClock()

    def create(
        self,
        *,
        experiment_id: str,
        framework: str,
        provider: str,
        model: str,
        config_path: Path,
        config_hash: str,
        dataset_name: str,
        dataset_version: str,
        dataset_hash: str,
        seed: int,
        repetition_id: int,
        run_id: str | None = None,
    ) -> tuple[RunPaths, RunManifest]:
        git_commit = current_git_commit()
        selected_id = run_id or DefaultIdGenerator().new_run_id(
            framework, model, dataset_version, git_commit
        )
        validate_run_id(selected_id)
        root = self.runs_root / experiment_id / selected_id
        if root.exists():
            raise FileExistsError(f"Run directory already exists: {root}")
        paths = self._create_layout(root)
        manifest = RunManifest(
            schema_version=SCHEMA_VERSION,
            project_version=__version__,
            experiment_id=experiment_id,
            run_id=selected_id,
            status=RunStatus.RUNNING,
            started_at=self.clock.now_iso(),
            completed_at=None,
            git_commit=git_commit,
            python_version=platform.python_version(),
            dependency_versions=dependency_versions(),
            framework=framework,
            provider=provider,
            model=model,
            model_call_date=None,
            config_path=str(config_path),
            config_hash=config_hash,
            dataset_name=dataset_name,
            dataset_version=dataset_version,
            dataset_hash=dataset_hash,
            seed=seed,
            repetition_id=repetition_id,
        )
        write_json_atomic(paths.manifest, manifest)
        return paths, manifest

    def complete(
        self,
        paths: RunPaths,
        manifest: RunManifest,
        token_usage: ProviderUsage | None = None,
    ) -> RunManifest:
        outputs = self._outputs(paths)
        completed = replace(
            manifest,
            status=RunStatus.COMPLETED,
            completed_at=self.clock.now_iso(),
            model_call_date=self.clock.now_iso()[:10] if manifest.provider != "mock" else None,
            outputs={name: path.relative_to(paths.root).as_posix() for name, path in outputs.items()},
            output_hashes={name: file_hash(path) for name, path in outputs.items()},
            token_usage=token_usage or ProviderUsage(),
        )
        write_json_atomic(paths.manifest, completed)
        return completed

    def fail(self, paths: RunPaths, manifest: RunManifest, reason: str) -> RunManifest:
        failed = replace(
            manifest,
            status=RunStatus.FAILED,
            completed_at=self.clock.now_iso(),
            failure_reason=redact_text(reason)[:1000],
        )
        write_json_atomic(paths.manifest, failed)
        return failed

    @staticmethod
    def _create_layout(root: Path) -> RunPaths:
        paths = RunPaths(
            root=root,
            manifest=root / "manifest.json",
            log=root / "logs" / "run.log",
            traces=root / "traces" / "invocations.jsonl",
            invocation_metrics=root / "metrics" / "invocations.csv",
            task_metrics=root / "metrics" / "tasks.csv",
            summary=root / "reports" / "summary.json",
            rq_evidence=root / "reports" / "rq_evidence.json",
            tables=root / "reports" / "tables",
            figures=root / "reports" / "figures",
        )
        for directory in (
            paths.log.parent,
            paths.traces.parent,
            paths.invocation_metrics.parent,
            paths.tables,
            paths.figures,
        ):
            directory.mkdir(parents=True, exist_ok=False)
        return paths

    @staticmethod
    def _outputs(paths: RunPaths) -> dict[str, Path]:
        outputs: dict[str, Path] = {}
        for path in sorted(item for item in paths.root.rglob("*") if item.is_file()):
            if path == paths.manifest or path.suffix == ".tmp":
                continue
            relative = path.relative_to(paths.root).as_posix()
            outputs[relative] = path
        return outputs


def current_git_commit(project_root: str | Path | None = None) -> str:
    command = ["git"]
    if project_root is not None:
        command.extend(["-C", str(Path(project_root).resolve())])
    command.extend(["rev-parse", "HEAD"])
    try:
        return subprocess.check_output(
            command,
            text=True,
            encoding="utf-8",
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "0000000"


def require_clean_git_worktree(project_root: str | Path) -> None:
    root = Path(project_root).resolve()
    try:
        output = subprocess.check_output(
            [
                "git",
                "-C",
                str(root),
                "status",
                "--porcelain",
                "--untracked-files=all",
            ],
            text=True,
            encoding="utf-8",
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError("Real-provider runs require a readable Git worktree") from error
    if output.strip():
        raise RuntimeError(
            "Real-provider runs require a clean Git worktree so the manifest commit "
            "matches the executed code"
        )


def dependency_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in ("langchain-core",):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not-installed"
    return versions


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
