"""Build independent evidence from immutable traces and adjudicated labels."""

from __future__ import annotations

import json
from pathlib import Path

from context_auditor.adapters.storage.runs import file_hash
from context_auditor.adapters.storage.serialization import (
    dumps,
    write_json_atomic,
)
from context_auditor.application.analysis import AnalyzeBloat
from context_auditor.application.conclusions import BuildRQEvidence
from context_auditor.application.external_annotations import (
    attach_adjudicated_annotations,
    load_bundle,
)
from context_auditor.domain.models import SCHEMA_VERSION


class BuildExternalEvidence:
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root)

    def execute(
        self,
        bundle_path: str | Path,
        adjudication_path: str | Path,
        answer_key_path: str | Path,
        output_dir: str | Path,
        *,
        annotation_set_id: str,
    ) -> Path:
        destination = Path(output_dir)
        if destination.exists():
            raise FileExistsError(
                f"External evidence output already exists: {destination}"
            )
        traces, study_manifest = load_bundle(Path(bundle_path))
        annotated = attach_adjudicated_annotations(
            traces,
            adjudication_path,
            answer_key_path,
            annotation_set_id=annotation_set_id,
        )
        final_natural = [
            trace
            for trace in annotated
            if trace.evidence_tier == "natural" and trace.task_success is not None
        ]
        incomplete = [
            trace.trace_id
            for trace in final_natural
            if len(trace.reference_annotations) != len(trace.segments)
        ]
        if incomplete:
            raise ValueError(
                "Every final natural trace must have one adjudicated annotation per "
                "segment; incomplete traces: "
                + ", ".join(incomplete[:10])
            )
        summary = AnalyzeBloat().execute(annotated)
        rules = json.loads(
            (
                self.project_root
                / "configs"
                / "conclusions"
                / "rq_rules_v2.json"
            ).read_text(encoding="utf-8")
        )
        evidence = BuildRQEvidence().execute(summary, rules)
        destination.mkdir(parents=True)
        write_json_atomic(destination / "summary.json", summary)
        write_json_atomic(destination / "rq_evidence.json", evidence)
        write_json_atomic(
            destination / "evidence_manifest.json",
            {
                "schema_version": SCHEMA_VERSION,
                "source_study_id": study_manifest["study_id"],
                "annotation_set_id": annotation_set_id,
                "final_natural_trace_count": len(final_natural),
                "independent_task_count": len(
                    {trace.task_id for trace in final_natural}
                ),
                "reference_type": "adjudicated_human_labels",
                "source_bundle_sha256": file_hash(Path(bundle_path)),
                "adjudication_sha256": file_hash(Path(adjudication_path)),
                "answer_key_sha256": file_hash(Path(answer_key_path)),
            },
        )
        annotation_path = destination / "reference_annotations.jsonl"
        annotation_path.write_text(
            "".join(
                dumps(
                    {
                        "trace_id": trace.trace_id,
                        "annotations": trace.reference_annotations,
                    }
                )
                + "\n"
                for trace in final_natural
            ),
            encoding="utf-8",
        )
        return destination
