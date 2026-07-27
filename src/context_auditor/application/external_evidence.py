"""Build independent evidence from immutable traces and adjudicated labels."""

from __future__ import annotations

from pathlib import Path

from context_auditor.adapters.storage.runs import file_hash
from context_auditor.adapters.storage.serialization import (
    dumps,
    write_json_atomic,
)
from context_auditor.application.external_annotations import (
    annotation_eligible_segment,
    attach_adjudicated_annotations,
    load_bundle,
)
from context_auditor.application.external_statistics import (
    build_study_b_statistics,
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
            if len(trace.reference_annotations)
            != sum(
                annotation_eligible_segment(segment)
                for segment in trace.segments
            )
        ]
        if incomplete:
            raise ValueError(
                "Every final natural trace must have one adjudicated annotation per "
                "segment; incomplete traces: "
                + ", ".join(incomplete[:10])
            )
        statistics = build_study_b_statistics(final_natural)
        summary = {
            "schema_version": SCHEMA_VERSION,
            "study": "B",
            "trace_count": len(final_natural),
            "independent_task_count": len(
                {trace.task_id for trace in final_natural}
            ),
            "frameworks": sorted(
                {trace.framework for trace in final_natural}
            ),
            "statistics": statistics,
        }
        primary = statistics["by_policy"]["primary"]
        evidence = {
            "schema_version": SCHEMA_VERSION,
            "study": "B",
            "conclusion_policy": (
                "Effect estimates, confidence intervals, sample sizes, and "
                "error patterns are reported without Supported/Not-supported "
                "threshold labels."
            ),
            "research_questions": {
                "RQ1": {
                    "evidence_type": "independent_human_reference",
                    "metrics": primary[
                        "rq1_detection_and_localization"
                    ],
                },
                "RQ2": {
                    "human_reference_validity": primary[
                        "rq2_human_measurement_validity"
                    ],
                    "counterfactual_validity": (
                        "reported separately in Study C"
                    ),
                },
                "RQ3": {
                    "evidence_type": "descriptive_natural_trace",
                    "metrics": primary["rq3_source_patterns"],
                },
                "RQ4": {
                    "evidence_type": "not_evaluated_in_study_b",
                },
            },
            "uncertain_sensitivity": {
                key: value
                for key, value in statistics["by_policy"].items()
                if key != "primary"
            },
        }
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
