"""Immutable, versioned file dataset repository."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class FileDatasetRepository:
    def __init__(self, data_root: str | Path) -> None:
        self.data_root = Path(data_root)

    def dataset_path(self, dataset_name: str, version: str) -> Path:
        path = self.data_root / "datasets" / dataset_name / version
        if not path.is_dir():
            raise FileNotFoundError(f"Dataset version does not exist: {path}")
        return path

    def load(self, dataset_name: str, version: str) -> dict[str, Any]:
        path = self.dataset_path(dataset_name, version)
        return {
            "tasks": self._load_json(path / "tasks.json"),
            "documents": self._load_json(path / "documents.json")
            if (path / "documents.json").is_file()
            else [],
            "memory": self._load_json(path / "memory.json")
            if (path / "memory.json").is_file()
            else [],
            "manifest": self._load_json(path / "dataset_manifest.json"),
        }

    def content_hash(self, dataset_name: str, version: str) -> str:
        path = self.dataset_path(dataset_name, version)
        digest = hashlib.sha256()
        for file_path in sorted(path.glob("*.json")):
            digest.update(file_path.name.encode("utf-8"))
            digest.update(file_path.read_bytes())
        return digest.hexdigest()

    @staticmethod
    def _load_json(path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))
