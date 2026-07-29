"""Fail-closed OSF evidence-chain gates for external-validation calls."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

from context_auditor.adapters.storage.serialization import write_json_atomic

MANIFEST_NAME = "osf_registration_manifest_v1.2.1.json"
OSF_REGISTRATION_RE = re.compile(
    r"^https://osf\.io/[a-z0-9]+(?:/overview)?/?$",
    re.IGNORECASE,
)

EVIDENCE_BLOCKS = {
    "initial_registration": "initial_required_files",
    "calibration_method_clarification": "clarification_required_files",
    "calibration_implementation_correction": "correction_required_files",
    "calibration_addendum": "addendum_required_files",
}
PHASE_CHAINS = {
    "calibration": (
        "initial_registration",
        "calibration_method_clarification",
        "calibration_implementation_correction",
    ),
    "test": (
        "initial_registration",
        "calibration_method_clarification",
        "calibration_implementation_correction",
        "calibration_addendum",
    ),
}
FREEZE_PHASES = {
    "initial": "initial_registration",
    "calibration": "initial_registration",
    "clarification": "calibration_method_clarification",
    "correction": "calibration_implementation_correction",
    "addendum": "calibration_addendum",
    "test": "calibration_addendum",
}


def protocol_manifest_path(project_root: str | Path) -> Path:
    return Path(project_root) / "thesis" / "plans" / MANIFEST_NAME


def protocol_manifest_hash(project_root: str | Path) -> str:
    return hashlib.sha256(protocol_manifest_path(project_root).read_bytes()).hexdigest()


def validate_protocol_registration(
    project_root: str | Path,
    *,
    phase: str = "test",
) -> dict:
    """Validate the complete immutable evidence chain for a call phase."""
    if phase not in PHASE_CHAINS:
        raise ValueError(f"Unsupported protocol phase: {phase}")
    root = Path(project_root).resolve()
    manifest_path = protocol_manifest_path(root)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    validated = []
    predecessor_url = None
    for block_name in PHASE_CHAINS[phase]:
        block = data.get(block_name, {})
        validated.append(
            _validate_evidence_block(
                root,
                manifest_path,
                block_name,
                block,
                predecessor_url=predecessor_url,
            )
        )
        predecessor_url = str(block["registration_url"])

    active_name = PHASE_CHAINS[phase][-1]
    active = data[active_name]
    _validate_current_runtime_files(manifest_path, active)
    return {
        "valid": True,
        "phase": phase,
        "derived_calls_allowed": True,
        "registration_url": active["registration_url"],
        "registered_at": active["registered_at"],
        "evidence_chain": validated,
        "file_count": len(active["file_sha256"]),
        "manifest_sha256": protocol_manifest_hash(root),
    }


def _validate_evidence_block(
    root: Path,
    manifest_path: Path,
    block_name: str,
    block: dict,
    *,
    predecessor_url: str | None,
) -> dict:
    if block.get("registration_status") != "registered":
        raise RuntimeError(
            f"Calls are blocked until {block_name} is registered on OSF"
        )
    registration_url = str(block.get("registration_url", "")).strip()
    if not OSF_REGISTRATION_RE.fullmatch(registration_url):
        raise RuntimeError(f"{block_name} has an invalid OSF registration URL")
    registered_at = str(block.get("registered_at", "")).strip()
    try:
        datetime.fromisoformat(registered_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise RuntimeError(f"{block_name} has an invalid registration time") from error
    if predecessor_url is not None:
        observed = str(block.get("predecessor_registration_url", "")).strip()
        if observed != predecessor_url:
            raise RuntimeError(
                f"{block_name} does not reference the preceding registration"
            )

    package_reference = str(block.get("protocol_package", "")).strip()
    package = _workspace_path(root, package_reference)
    if not package.is_file():
        raise FileNotFoundError(f"Registered protocol package is missing: {package}")
    expected_package_hash = str(
        block.get("protocol_package_sha256", "")
    ).strip()
    observed_package_hash = hashlib.sha256(package.read_bytes()).hexdigest()
    if observed_package_hash != expected_package_hash:
        raise RuntimeError(f"Registered protocol package hash mismatch: {package}")

    expected_files = block.get("file_sha256", {})
    if not expected_files:
        raise RuntimeError(f"{block_name} lacks frozen file hashes")
    archive_files = _validate_package_contents(package, block_name)
    if archive_files != expected_files:
        raise RuntimeError(
            f"{block_name} package file manifest differs from the local manifest"
        )

    release_tag = str(block.get("github_release_tag", "")).strip()
    release_commit = str(block.get("github_release_commit", "")).strip()
    if not release_tag or not release_commit:
        raise RuntimeError(f"{block_name} lacks GitHub release tag/commit evidence")
    resolved_commit = _git_output(
        root,
        "rev-parse",
        f"refs/tags/{release_tag}^{{commit}}",
    )
    if resolved_commit != release_commit:
        raise RuntimeError(f"{block_name} release tag does not resolve to its commit")
    _validate_package_at_commit(root, package_reference, release_commit, expected_package_hash)
    return {
        "block": block_name,
        "registration_url": registration_url,
        "registered_at": registered_at,
        "package_sha256": expected_package_hash,
        "release_tag": release_tag,
        "release_commit": release_commit,
        "file_count": len(expected_files),
    }


def _validate_package_contents(package: Path, block_name: str) -> dict[str, str]:
    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
        if "package_manifest.json" in names:
            package_manifest = json.loads(archive.read("package_manifest.json"))
            if package_manifest.get("evidence_block") != block_name:
                raise RuntimeError("Protocol package evidence block is inconsistent")
            files = package_manifest.get("files", {})
            result = {}
            for relative, item in files.items():
                archive_path = str(item["archive_path"])
                expected = str(item["sha256"])
                if archive_path not in names:
                    raise RuntimeError(f"Protocol package member is missing: {archive_path}")
                observed = hashlib.sha256(archive.read(archive_path)).hexdigest()
                if observed != expected:
                    raise RuntimeError(
                        f"Protocol package member hash mismatch: {archive_path}"
                    )
                result[str(relative)] = expected
            return result

        if "registration_manifest.json" not in names:
            raise RuntimeError("Protocol package has no frozen manifest")
        frozen = json.loads(archive.read("registration_manifest.json"))
        files = frozen.get(block_name, {}).get("file_sha256", {})
        for relative, expected in files.items():
            archive_path = "inputs/" + PurePosixPath(relative).name
            if archive_path not in names:
                raise RuntimeError(f"Protocol package member is missing: {archive_path}")
            observed = hashlib.sha256(archive.read(archive_path)).hexdigest()
            if observed != expected:
                raise RuntimeError(
                    f"Protocol package member hash mismatch: {archive_path}"
                )
        return {str(key): str(value) for key, value in files.items()}


def _validate_current_runtime_files(manifest_path: Path, block: dict) -> None:
    base = manifest_path.parent
    for relative, expected in block.get("file_sha256", {}).items():
        path = (base / relative).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Frozen runtime file is missing: {path}")
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
        if observed != expected:
            raise RuntimeError(f"Frozen runtime file changed: {path}")


def _validate_package_at_commit(
    root: Path,
    package_reference: str,
    commit: str,
    expected_hash: str,
) -> None:
    git_path = package_reference.replace("\\", "/")
    payload = subprocess.run(
        ["git", "show", f"{commit}:{git_path}"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    if hashlib.sha256(payload).hexdigest() != expected_hash:
        raise RuntimeError("GitHub release commit does not contain the registered package")


def _git_output(root: Path, *arguments: str) -> str:
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError(
            "Protocol evidence cannot be verified against local Git history"
        ) from error


def _workspace_path(root: Path, reference: str) -> Path:
    if not reference:
        raise RuntimeError("Protocol package path is empty")
    path = (root / reference).resolve()
    if path != root and root not in path.parents:
        raise RuntimeError(f"Protocol package escapes the project root: {path}")
    return path


def freeze_protocol_package(
    project_root: str | Path,
    output_path: str | Path,
    *,
    phase: str = "clarification",
) -> Path:
    """Freeze one evidence package; registration fields remain fail-closed."""
    if phase not in FREEZE_PHASES:
        raise ValueError(f"Unsupported protocol phase: {phase}")
    block_name = FREEZE_PHASES[phase]
    root = Path(project_root).resolve()
    manifest_path = protocol_manifest_path(root)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    required_key = EVIDENCE_BLOCKS[block_name]
    base = manifest_path.parent
    files: dict[str, Path] = {}
    hashes: dict[str, str] = {}
    for relative in data.get(required_key, []):
        path = (base / relative).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Protocol input is missing: {path}")
        files[relative] = path
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not files:
        raise ValueError(f"Protocol manifest has no {required_key}")

    target = Path(output_path).resolve()
    if target.exists():
        raise FileExistsError(f"Protocol package already exists: {target}")
    if target != root and root not in target.parents:
        raise RuntimeError("Protocol package must be created inside the project")
    target.parent.mkdir(parents=True, exist_ok=True)
    target_reference = target.relative_to(root).as_posix()
    implementation_commit = _git_output(root, "rev-parse", "HEAD")
    predecessor = _predecessor_url(data, block_name)
    members = {
        relative: {
            "archive_path": f"inputs/{index:02d}_{path.name}",
            "sha256": hashes[relative],
        }
        for index, (relative, path) in enumerate(sorted(files.items()), start=1)
    }
    package_manifest = {
        "protocol_version": data.get("protocol_version"),
        "evidence_block": block_name,
        "implementation_commit": implementation_commit,
        "predecessor_registration_url": predecessor,
        "files": members,
    }
    block = {
        **data.get(block_name, {}),
        "registration_status": "ready_for_registration",
        "registration_url": "",
        "registered_at": "",
        "predecessor_registration_url": predecessor,
        "github_release_tag": "",
        "github_release_commit": "",
        "file_sha256": hashes,
        "protocol_package": target_reference,
        "protocol_package_sha256": "",
    }
    frozen = {**data, block_name: block}
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, path in sorted(files.items()):
            archive.write(path, members[relative]["archive_path"])
        archive.writestr(
            "package_manifest.json",
            json.dumps(package_manifest, indent=2, sort_keys=True) + "\n",
        )
        archive.writestr(
            "registration_manifest.json",
            json.dumps(frozen, indent=2, sort_keys=True) + "\n",
        )
    block["protocol_package_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    write_json_atomic(manifest_path, {**data, block_name: block})
    return target


def _predecessor_url(data: dict, block_name: str) -> str:
    if block_name == "calibration_method_clarification":
        return str(data.get("initial_registration", {}).get("registration_url", ""))
    if block_name == "calibration_implementation_correction":
        return str(
            data.get("calibration_method_clarification", {}).get(
                "registration_url",
                "",
            )
        )
    if block_name == "calibration_addendum":
        return str(
            data.get("calibration_implementation_correction", {}).get(
                "registration_url",
                "",
            )
        )
    return ""
