"""Externally timestamped protocol gates for calibration and held-out calls."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from context_auditor.adapters.storage.serialization import write_json_atomic

MANIFEST_NAME = "osf_registration_manifest_v1.2.1.json"
PHASES = {
    "calibration": {
        "block": "initial_registration",
        "required": "initial_required_files",
        "allow": "calibration_calls_allowed",
    },
    "test": {
        "block": "calibration_addendum",
        "required": "addendum_required_files",
        "allow": "heldout_calls_allowed",
    },
}


def protocol_manifest_path(project_root: str | Path) -> Path:
    return (
        Path(project_root)
        / "thesis"
        / "plans"
        / MANIFEST_NAME
    )


def protocol_manifest_hash(project_root: str | Path) -> str:
    return hashlib.sha256(
        protocol_manifest_path(project_root).read_bytes()
    ).hexdigest()


def validate_protocol_registration(
    project_root: str | Path,
    *,
    phase: str = "test",
) -> dict:
    if phase not in PHASES:
        raise ValueError(f"Unsupported protocol phase: {phase}")
    manifest_path = protocol_manifest_path(project_root)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    definition = PHASES[phase]
    block = data.get(definition["block"], {})
    if block.get("registration_status") != "registered":
        raise RuntimeError(
            f"Real {phase} calls are blocked until the v1.2.1 "
            f"{definition['block']} is registered on OSF"
        )
    if not block.get(definition["allow"]):
        raise RuntimeError(
            f"The protocol manifest has not enabled real {phase} calls"
        )
    if not str(block.get("registration_url", "")).startswith("http"):
        raise RuntimeError(
            f"The {definition['block']} lacks an OSF registration URL"
        )
    expected_hashes = block.get("file_sha256", {})
    if not expected_hashes:
        raise RuntimeError(
            f"The {definition['block']} lacks frozen file hashes"
        )
    base = manifest_path.parent
    for relative, expected in expected_hashes.items():
        path = (base / relative).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Frozen protocol file is missing: {path}")
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
        if observed != expected:
            raise RuntimeError(
                f"Frozen protocol file changed after registration: {path}"
            )
    return {
        "valid": True,
        "phase": phase,
        "registration_url": block["registration_url"],
        "registered_at": block.get("registered_at"),
        "file_count": len(expected_hashes),
        "manifest_sha256": protocol_manifest_hash(project_root),
    }


def freeze_protocol_package(
    project_root: str | Path,
    output_path: str | Path,
    *,
    phase: str = "calibration",
) -> Path:
    if phase not in PHASES:
        raise ValueError(f"Unsupported protocol phase: {phase}")
    root = Path(project_root)
    manifest_path = protocol_manifest_path(root)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    definition = PHASES[phase]
    base = manifest_path.parent
    files: dict[str, Path] = {}
    hashes: dict[str, str] = {}
    for relative in data.get(definition["required"], []):
        path = (base / relative).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Protocol input is missing: {path}")
        files[relative] = path
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not files:
        raise ValueError(f"Protocol manifest has no {phase} required files")
    block = {
        **data.get(definition["block"], {}),
        "registration_status": "ready_for_registration",
        "registration_url": "",
        "registered_at": "",
        definition["allow"]: False,
        "file_sha256": hashes,
        "note": (
            "Upload this package to an immutable OSF registration, then record "
            "the URL and timestamp and explicitly enable the corresponding calls."
        ),
    }
    frozen = {**data, definition["block"]: block}
    target = Path(output_path)
    if target.exists():
        raise FileExistsError(f"Protocol package already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, path in sorted(files.items()):
            archive.write(path, "inputs/" + Path(relative).name)
        archive.writestr(
            "registration_manifest.json",
            json.dumps(frozen, indent=2, sort_keys=True) + "\n",
        )
    block["protocol_package"] = str(
        target.resolve().relative_to(root.resolve())
    ).replace("\\", "/")
    block["protocol_package_sha256"] = hashlib.sha256(
        target.read_bytes()
    ).hexdigest()
    write_json_atomic(
        manifest_path,
        {**data, definition["block"]: block},
    )
    return target
