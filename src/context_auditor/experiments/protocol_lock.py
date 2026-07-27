"""Externally timestamped protocol gate for paid held-out execution."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from context_auditor.adapters.storage.serialization import write_json_atomic


def validate_protocol_registration(project_root: str | Path) -> dict:
    root = Path(project_root)
    manifest_path = (
        root / "thesis" / "plans" / "osf_registration_manifest_v1.2.json"
    )
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("registration_status") != "registered":
        raise RuntimeError(
            "Paid held-out calls are blocked until the v1.2 protocol is "
            "externally registered on OSF"
        )
    if not data.get("paid_test_calls_allowed"):
        raise RuntimeError("The protocol manifest has not enabled paid test calls")
    if not str(data.get("registration_url", "")).startswith("http"):
        raise RuntimeError("The protocol manifest lacks a registration URL")
    expected_hashes = data.get("file_sha256", {})
    if not expected_hashes:
        raise RuntimeError("The protocol manifest lacks frozen file hashes")
    base = manifest_path.parent
    for relative, expected in expected_hashes.items():
        path = (base / relative).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Frozen protocol file is missing: {path}")
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
        if observed != expected:
            raise RuntimeError(f"Frozen protocol file changed after registration: {path}")
    return {
        "valid": True,
        "registration_url": data["registration_url"],
        "registered_at": data.get("registered_at"),
        "file_count": len(expected_hashes),
    }


def freeze_protocol_package(
    project_root: str | Path,
    output_path: str | Path,
) -> Path:
    root = Path(project_root)
    manifest_path = (
        root / "thesis" / "plans" / "osf_registration_manifest_v1.2.json"
    )
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = manifest_path.parent
    files: dict[str, Path] = {}
    hashes: dict[str, str] = {}
    for relative in data.get("required_files", []):
        path = (base / relative).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Protocol input is missing: {path}")
        files[relative] = path
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not files:
        raise ValueError("Protocol manifest has no required files")
    frozen = {
        **data,
        "registration_status": "ready_for_registration",
        "registration_url": "",
        "registered_at": "",
        "paid_test_calls_allowed": False,
        "file_sha256": hashes,
        "note": (
            "Upload the protocol package to an immutable OSF registration, "
            "then add its URL/timestamp and explicitly enable paid calls."
        ),
    }
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
    frozen["protocol_package"] = str(
        target.resolve().relative_to(root.resolve())
    ).replace("\\", "/")
    frozen["protocol_package_sha256"] = hashlib.sha256(
        target.read_bytes()
    ).hexdigest()
    write_json_atomic(manifest_path, frozen)
    return target
