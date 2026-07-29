"""CLI entry point for named, reproducible experiment runs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from context_auditor import __version__
from context_auditor.adapters.common import DefaultIdGenerator, RegexTokenizer, UtcClock
from context_auditor.adapters.providers import DeepSeekProvider
from context_auditor.adapters.storage import FileDatasetRepository, JsonlTraceRepository, RunRegistry
from context_auditor.adapters.storage.serialization import write_json_atomic
from context_auditor.application import CaptureContext
from context_auditor.application.annotations import export_blind_review_package
from context_auditor.application.comparison import CompareFrameworks
from context_auditor.application.detector_calibration import (
    apply_selected_thresholds,
    calibrate_detector,
)
from context_auditor.application.external_annotations import (
    adjudicate_annotation_files,
    export_context_annotation_packages,
    import_context_annotation_file,
)
from context_auditor.application.external_evidence import BuildExternalEvidence
from context_auditor.application.outcome_annotations import (
    adjudicate_outcome_files,
    build_outcome_validation_evidence,
    export_outcome_annotation_packages,
)
from context_auditor.application.reporting import write_csv
from context_auditor.application.study_c_evidence import build_study_c_evidence
from context_auditor.application.study_bundle import ExportStudyBundle, validate_study_bundle
from context_auditor.domain.enums import PrivacyMode
from context_auditor.domain.models import (
    CaptureRequest,
    Message,
    ModelRequestEnvelope,
    SCHEMA_VERSION,
)
from context_auditor.domain.text import hash_text
from context_auditor.experiments import (
    RunExperiment,
    RunExternalValidation,
    RunFormalExperiment,
    RunStudyC,
    load_external_validation_config,
    load_experiment_config,
    load_study_c_config,
)
from context_auditor.experiments.dataset_validation import validate_dataset
from context_auditor.experiments.external_dataset import (
    prepare_external_validation_dataset,
)
from context_auditor.experiments.protocol_lock import freeze_protocol_package


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="context-auditor")
    parser.add_argument("--version", action="version", version=f"context-auditor {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run one versioned experiment config.")
    run.add_argument("--config", required=True)
    run.add_argument("--project-root", default=".")
    run.add_argument("--run-id")

    formal = subparsers.add_parser(
        "run-formal",
        help="Run one formal provider-backed experiment config.",
    )
    formal.add_argument("--config", required=True)
    formal.add_argument("--project-root", default=".")
    formal.add_argument("--run-id")
    formal.add_argument("--confirm-real-cost", action="store_true")

    formal_suite = subparsers.add_parser(
        "run-formal-suite",
        help="Run the formal Custom ReAct and LangChain configs.",
    )
    formal_suite.add_argument(
        "--custom-config",
        default="configs/experiments/formal_custom_react_deepseek_v1.json",
    )
    formal_suite.add_argument(
        "--langchain-config",
        default="configs/experiments/formal_langchain_deepseek_v1.json",
    )
    formal_suite.add_argument("--project-root", default=".")
    formal_suite.add_argument("--confirm-real-cost", action="store_true")

    suite = subparsers.add_parser("run-suite", help="Run custom ReAct and LangChain configs.")
    suite.add_argument(
        "--custom-config",
        default="configs/experiments/pilot_custom_react_v1.json",
    )
    suite.add_argument(
        "--langchain-config",
        default="configs/experiments/pilot_langchain_v1.json",
    )
    suite.add_argument("--project-root", default=".")

    check = subparsers.add_parser("check-provider", help="Check secret presence without printing values.")
    check.add_argument("--provider", choices=("mock", "deepseek"), required=True)
    check.add_argument("--model", default="deepseek-v4-flash")

    smoke = subparsers.add_parser("run-real-model-smoke", help="Run one named DeepSeek smoke test.")
    smoke.add_argument("--project-root", default=".")
    smoke.add_argument("--model", default="deepseek-v4-flash")
    smoke.add_argument(
        "--prompt",
        default="Answer in one short sentence: what is context bloat in an LLM agent?",
    )
    smoke.add_argument("--privacy-mode", choices=[item.value for item in PrivacyMode], default="redacted")

    dataset = subparsers.add_parser(
        "validate-dataset",
        help="Validate a versioned formal-study dataset.",
    )
    dataset.add_argument("--project-root", default=".")
    dataset.add_argument("--dataset-name", default="context_bloat_benchmark")
    dataset.add_argument("--dataset-version", default="v1")

    export = subparsers.add_parser(
        "export-study",
        help="Export completed component runs as a validated study ZIP.",
    )
    export.add_argument("--project-root", default=".")
    export.add_argument("--run", action="append", required=True)
    export.add_argument("--output", required=True)
    export.add_argument("--public-demo", action="store_true")

    validate = subparsers.add_parser(
        "validate-study",
        help="Validate a study bundle without extracting it.",
    )
    validate.add_argument("--bundle", required=True)
    annotations = subparsers.add_parser(
        "export-annotations",
        help="Export deterministic condition-blind review forms from a study bundle.",
    )
    annotations.add_argument("--bundle", required=True)
    annotations.add_argument("--output", required=True)
    annotations.add_argument("--seed", type=int, default=20260726)

    prepare_external = subparsers.add_parser(
        "prepare-external-dataset",
        help="Build the pinned 12-calibration/60-test external dataset.",
    )
    prepare_external.add_argument("--hotpot", required=True)
    prepare_external.add_argument("--longmemeval", required=True)
    prepare_external.add_argument("--bfcl", required=True)
    prepare_external.add_argument(
        "--output",
        default="data/datasets/external_validation/v1",
    )
    prepare_external.add_argument("--seed", type=int, default=20260727)

    run_external = subparsers.add_parser(
        "run-external",
        help="Run one natural-trace external-validation config.",
    )
    run_external.add_argument("--config", required=True)
    run_external.add_argument("--project-root", default=".")
    run_external.add_argument("--run-id")
    run_external.add_argument("--confirm-real-cost", action="store_true")

    run_external_suite = subparsers.add_parser(
        "run-external-suite",
        help="Run paired Custom ReAct and LangChain natural-trace configs.",
    )
    run_external_suite.add_argument(
        "--custom-config",
        default="configs/experiments/external_custom_react_v1.2.1.json",
    )
    run_external_suite.add_argument(
        "--langchain-config",
        default="configs/experiments/external_langchain_v1.2.1.json",
    )
    run_external_suite.add_argument("--project-root", default=".")
    run_external_suite.add_argument("--confirm-real-cost", action="store_true")

    context_annotations = subparsers.add_parser(
        "export-context-annotations",
        help="Export full-overlap double-blind context-segment forms.",
    )
    context_annotations.add_argument("--bundle", required=True)
    context_annotations.add_argument("--output", required=True)
    context_annotations.add_argument("--project-root", default=".")
    context_annotations.add_argument("--annotation-set-id", required=True)
    context_annotations.add_argument(
        "--include-split",
        choices=("calibration", "test"),
        required=True,
    )

    import_context_annotations = subparsers.add_parser(
        "import-context-annotations",
        help="Validate and freeze one completed blinded context review.",
    )
    import_context_annotations.add_argument("--reviewer", required=True)
    import_context_annotations.add_argument(
        "--annotation-linkage",
        required=True,
    )
    import_context_annotations.add_argument("--output", required=True)
    import_context_annotations.add_argument("--annotation-set-id", required=True)
    import_context_annotations.add_argument("--reviewer-id", required=True)

    adjudicate = subparsers.add_parser(
        "adjudicate-annotations",
        help="Compute agreement and create a consensus adjudication form.",
    )
    adjudicate.add_argument("--reviewer-a", required=True)
    adjudicate.add_argument("--reviewer-b", required=True)
    adjudicate.add_argument("--annotation-linkage", required=True)
    adjudicate.add_argument("--output", required=True)
    adjudicate.add_argument("--annotation-set-id", required=True)

    calibrate = subparsers.add_parser(
        "calibrate-detector",
        help="Select heuristic thresholds from calibration-only human labels.",
    )
    calibrate.add_argument("--context-bundle", required=True)
    calibrate.add_argument("--reviewer-a", required=True)
    calibrate.add_argument("--reviewer-b", required=True)
    calibrate.add_argument("--adjudication", required=True)
    calibrate.add_argument("--annotation-linkage", required=True)
    calibrate.add_argument("--output", required=True)
    calibrate.add_argument("--annotation-set-id", required=True)

    apply_thresholds = subparsers.add_parser(
        "apply-calibrated-thresholds",
        help="Apply frozen calibration thresholds to held-out configs.",
    )
    apply_thresholds.add_argument("--selected-thresholds", required=True)
    apply_thresholds.add_argument(
        "--config",
        action="append",
        required=True,
        help="Held-out config path; repeat for both execution paths.",
    )
    apply_thresholds.add_argument("--audit-output", required=True)

    external_evidence = subparsers.add_parser(
        "build-external-evidence",
        help="Build RQ1-RQ3 evidence from immutable traces and adjudication.",
    )
    external_evidence.add_argument("--project-root", default=".")
    external_evidence.add_argument("--bundle", required=True)
    external_evidence.add_argument("--adjudication", required=True)
    external_evidence.add_argument("--annotation-linkage", required=True)
    external_evidence.add_argument("--output", required=True)
    external_evidence.add_argument("--annotation-set-id", required=True)

    study_c = subparsers.add_parser(
        "run-counterfactual-suite",
        help="Run the frozen Study C counterfactual and mitigation replay.",
    )
    study_c.add_argument("--project-root", default=".")
    study_c.add_argument(
        "--config",
        default="configs/experiments/study_c_v1.2.1.json",
    )
    study_c.add_argument("--bundle", required=True)
    study_c.add_argument("--adjudication", required=True)
    study_c.add_argument("--annotation-linkage", required=True)
    study_c.add_argument("--annotation-set-id", required=True)
    study_c.add_argument("--run-id")
    study_c.add_argument("--confirm-real-cost", action="store_true")

    outcome_annotations = subparsers.add_parser(
        "export-outcome-annotations",
        help="Export condition-blind task-outcome review forms.",
    )
    outcome_annotations.add_argument(
        "--traces",
        action="append",
        required=True,
        help="Trace JSONL path; repeat for multiple framework runs.",
    )
    outcome_annotations.add_argument("--output", required=True)
    outcome_annotations.add_argument("--annotation-set-id", required=True)
    outcome_annotations.add_argument(
        "--evidence-tier",
        action="append",
        dest="evidence_tiers",
    )
    outcome_annotations.add_argument(
        "--configuration",
        action="append",
        dest="configurations",
    )
    outcome_annotations.add_argument(
        "--outputs-per-block",
        type=int,
        default=24,
    )

    outcome_adjudication = subparsers.add_parser(
        "adjudicate-outcomes",
        help="Measure agreement and prepare consensus outcome decisions.",
    )
    outcome_adjudication.add_argument("--reviewer-a", required=True)
    outcome_adjudication.add_argument("--reviewer-b", required=True)
    outcome_adjudication.add_argument("--answer-key", required=True)
    outcome_adjudication.add_argument("--output", required=True)
    outcome_adjudication.add_argument("--annotation-set-id", required=True)

    study_c_evidence = subparsers.add_parser(
        "build-study-c-evidence",
        help="Build counterfactual and RQ4 evidence after outcome adjudication.",
    )
    study_c_evidence.add_argument("--traces", required=True)
    study_c_evidence.add_argument("--ledger", required=True)
    study_c_evidence.add_argument("--outcome-adjudication", required=True)
    study_c_evidence.add_argument("--outcome-answer-key", required=True)
    study_c_evidence.add_argument("--output", required=True)

    outcome_validation = subparsers.add_parser(
        "build-outcome-validation",
        help="Compare an automatic task scorer with adjudicated human outcomes.",
    )
    outcome_validation.add_argument("--traces", required=True)
    outcome_validation.add_argument("--outcome-adjudication", required=True)
    outcome_validation.add_argument("--outcome-answer-key", required=True)
    outcome_validation.add_argument("--output", required=True)

    freeze_protocol = subparsers.add_parser(
        "freeze-external-protocol",
        help="Build the immutable upload package required before paid test calls.",
    )
    freeze_protocol.add_argument("--project-root", default=".")
    freeze_protocol.add_argument(
        "--output",
        default="thesis/releases/osf_external_validation_protocol_v1.2.1.zip",
    )
    freeze_protocol.add_argument(
        "--phase",
        choices=("initial", "clarification", "addendum"),
        default="clarification",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        root = Path(args.project_root).resolve()
        config = load_experiment_config(root / args.config)
        run_path = RunExperiment(root).execute(config, run_id=args.run_id)
        print(run_path)
        return 0
    if args.command == "run-formal":
        root = Path(args.project_root).resolve()
        config = load_experiment_config(root / args.config)
        if config.provider != "mock" and not args.confirm_real_cost:
            print(
                "Real-provider formal runs require --confirm-real-cost because "
                "they can issue many paid API calls."
            )
            return 2
        print(RunFormalExperiment(root).execute(config, run_id=args.run_id))
        return 0
    if args.command == "run-formal-suite":
        root = Path(args.project_root).resolve()
        configs = [
            load_experiment_config(root / args.custom_config),
            load_experiment_config(root / args.langchain_config),
        ]
        if any(config.provider != "mock" for config in configs) and not args.confirm_real_cost:
            print(
                "Real-provider formal suites require --confirm-real-cost because "
                "they can issue many paid API calls."
            )
            return 2
        for config in configs:
            print(RunFormalExperiment(root).execute(config))
        return 0
    if args.command == "run-suite":
        root = Path(args.project_root).resolve()
        experiment_outputs = [
            RunExperiment(root).execute(load_experiment_config(root / args.custom_config)),
            RunExperiment(root).execute(load_experiment_config(root / args.langchain_config)),
        ]
        comparison_output = build_framework_comparison(
            root,
            experiment_outputs[0],
            experiment_outputs[1],
            root / args.custom_config,
            root / args.langchain_config,
        )
        outputs = [*experiment_outputs, comparison_output]
        for output in outputs:
            print(output)
        return 0
    if args.command == "check-provider":
        required = [] if args.provider == "mock" else ["DEEPSEEK_API_KEY"]
        status = {
            "provider": args.provider,
            "model": args.model,
            "required_environment": {
                name: "SET" if os.environ.get(name) else "UNSET" for name in required
            },
        }
        print(json.dumps(status, indent=2))
        return 0 if all(value == "SET" for value in status["required_environment"].values()) else 2
    if args.command == "run-real-model-smoke":
        return run_real_model_smoke(Path(args.project_root).resolve(), args)
    if args.command == "validate-dataset":
        root = Path(args.project_root).resolve()
        repository = FileDatasetRepository(root / "data")
        result = validate_dataset(
            repository.load(args.dataset_name, args.dataset_version)
        )
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "export-study":
        root = Path(args.project_root).resolve()
        output = ExportStudyBundle(root).execute(
            [root / path for path in args.run],
            root / args.output,
            public_demo=args.public_demo,
        )
        print(output)
        return 0
    if args.command == "validate-study":
        print(json.dumps(validate_study_bundle(args.bundle), indent=2))
        return 0
    if args.command == "export-annotations":
        print(
            export_blind_review_package(
                args.bundle,
                args.output,
                seed=args.seed,
            )
        )
        return 0
    if args.command == "prepare-external-dataset":
        print(
            prepare_external_validation_dataset(
                hotpot_path=args.hotpot,
                longmemeval_path=args.longmemeval,
                bfcl_path=args.bfcl,
                destination=args.output,
                seed=args.seed,
            )
        )
        return 0
    if args.command == "run-external":
        root = Path(args.project_root).resolve()
        config = load_external_validation_config(root / args.config)
        if config.provider != "mock" and not args.confirm_real_cost:
            print("Real external runs require --confirm-real-cost.")
            return 2
        print(
            RunExternalValidation(root).execute(
                config,
                run_id=args.run_id,
            )
        )
        return 0
    if args.command == "run-external-suite":
        root = Path(args.project_root).resolve()
        configs = [
            load_external_validation_config(root / args.custom_config),
            load_external_validation_config(root / args.langchain_config),
        ]
        if (
            any(config.provider != "mock" for config in configs)
            and not args.confirm_real_cost
        ):
            print("Real external suites require --confirm-real-cost.")
            return 2
        for config in configs:
            print(RunExternalValidation(root).execute(config))
        return 0
    if args.command == "export-context-annotations":
        root = Path(args.project_root).resolve()
        print(
            export_context_annotation_packages(
                args.bundle,
                args.output,
                project_root=root,
                annotation_set_id=args.annotation_set_id,
                include_split=args.include_split,
            )
        )
        return 0
    if args.command == "import-context-annotations":
        print(
            import_context_annotation_file(
                args.reviewer,
                args.annotation_linkage,
                args.output,
                annotation_set_id=args.annotation_set_id,
                reviewer_id=args.reviewer_id,
            )
        )
        return 0
    if args.command == "adjudicate-annotations":
        print(
            adjudicate_annotation_files(
                args.reviewer_a,
                args.reviewer_b,
                args.annotation_linkage,
                args.output,
                annotation_set_id=args.annotation_set_id,
            )
        )
        return 0
    if args.command == "calibrate-detector":
        print(
            calibrate_detector(
                args.context_bundle,
                args.reviewer_a,
                args.reviewer_b,
                args.adjudication,
                args.annotation_linkage,
                args.output,
                annotation_set_id=args.annotation_set_id,
            )
        )
        return 0
    if args.command == "apply-calibrated-thresholds":
        print(
            apply_selected_thresholds(
                args.selected_thresholds,
                args.config,
                args.audit_output,
            )
        )
        return 0
    if args.command == "build-external-evidence":
        root = Path(args.project_root).resolve()
        print(
            BuildExternalEvidence(root).execute(
                args.bundle,
                args.adjudication,
                args.annotation_linkage,
                args.output,
                annotation_set_id=args.annotation_set_id,
            )
        )
        return 0
    if args.command == "run-counterfactual-suite":
        root = Path(args.project_root).resolve()
        config = load_study_c_config(root / args.config)
        if config.provider != "mock" and not args.confirm_real_cost:
            print("Real Study C runs require --confirm-real-cost.")
            return 2
        print(
            RunStudyC(root).execute(
                config,
                bundle_path=args.bundle,
                adjudication_path=args.adjudication,
                annotation_linkage_path=args.annotation_linkage,
                annotation_set_id=args.annotation_set_id,
                run_id=args.run_id,
            )
        )
        return 0
    if args.command == "export-outcome-annotations":
        print(
            export_outcome_annotation_packages(
                args.traces,
                args.output,
                annotation_set_id=args.annotation_set_id,
                evidence_tiers=tuple(
                    args.evidence_tiers
                    or ("counterfactual", "mitigation")
                ),
                configurations=tuple(args.configurations or ()),
                outputs_per_block=args.outputs_per_block,
            )
        )
        return 0
    if args.command == "adjudicate-outcomes":
        print(
            adjudicate_outcome_files(
                args.reviewer_a,
                args.reviewer_b,
                args.answer_key,
                args.output,
                annotation_set_id=args.annotation_set_id,
            )
        )
        return 0
    if args.command == "build-study-c-evidence":
        print(
            build_study_c_evidence(
                args.traces,
                args.ledger,
                args.outcome_adjudication,
                args.outcome_answer_key,
                args.output,
            )
        )
        return 0
    if args.command == "build-outcome-validation":
        print(
            build_outcome_validation_evidence(
                args.traces,
                args.outcome_adjudication,
                args.outcome_answer_key,
                args.output,
            )
        )
        return 0
    if args.command == "freeze-external-protocol":
        root = Path(args.project_root).resolve()
        print(
            freeze_protocol_package(
                root,
                root / args.output,
                phase=args.phase,
            )
        )
        return 0
    return 1


def run_real_model_smoke(project_root: Path, args: argparse.Namespace) -> int:
    config_path = project_root / "configs" / "providers" / "deepseek_v4.json"
    config_hash = hash_text(config_path.read_text(encoding="utf-8") + args.prompt)
    datasets = FileDatasetRepository(project_root / "data")
    dataset_hash = datasets.content_hash("controlled_synthetic", "v1")
    registry = RunRegistry(project_root / "runs")
    paths, manifest = registry.create(
        experiment_id="deepseek-smoke-v1",
        framework="direct-provider",
        provider="deepseek",
        model=args.model,
        config_path=config_path,
        config_hash=config_hash,
        dataset_name="controlled_synthetic",
        dataset_version="v1",
        dataset_hash=dataset_hash,
        seed=42,
        repetition_id=0,
    )
    try:
        messages = (
            Message("system", "You are participating in a context auditing connectivity test."),
            Message("user", args.prompt),
        )
        envelope = ModelRequestEnvelope(messages=messages)
        response = DeepSeekProvider.from_environment(args.model).invoke(envelope)
        repository = JsonlTraceRepository(paths.traces)
        capture = CaptureContext(repository, RegexTokenizer(), UtcClock(), DefaultIdGenerator())
        trace = capture.execute(
            CaptureRequest(
                experiment_id=manifest.experiment_id,
                run_id=manifest.run_id,
                task_id="deepseek-smoke-001",
                framework=manifest.framework,
                provider=manifest.provider,
                model=manifest.model,
                configuration="smoke",
                workflow_family="provider_smoke",
                dataset_name=manifest.dataset_name,
                dataset_version=manifest.dataset_version,
                repetition_id=0,
                seed=42,
                invocation_index=0,
                messages=messages,
                config_hash=config_hash,
                request_envelope=envelope,
                provider_request=response.request_record,
                task_success=bool(response.content.strip()),
                task_output=response.content,
                expected_answer=None,
                provider_usage=response.usage,
                latency_ms=response.latency_ms,
                privacy_mode=PrivacyMode(args.privacy_mode),
            )
        )
        paths.log.write_text("DeepSeek smoke completed without storing credentials.\n", encoding="utf-8")
        write_json_atomic(
            paths.summary,
            {
                "schema_version": SCHEMA_VERSION,
                "trace_id": trace.trace_id,
                "provider": args.model,
                "response_chars": len(response.content),
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "latency_ms": response.latency_ms,
            },
        )
        registry.complete(paths, manifest, response.usage)
        print(paths.root)
        return 0
    except Exception as error:
        paths.log.write_text(f"Smoke failed: {type(error).__name__}\n", encoding="utf-8")
        registry.fail(paths, manifest, f"{type(error).__name__}: {error}")
        raise


def build_framework_comparison(
    project_root: Path,
    baseline_run: Path,
    comparison_run: Path,
    baseline_config: Path,
    comparison_config: Path,
) -> Path:
    baseline = json.loads(
        (baseline_run / "reports" / "summary.json").read_text(encoding="utf-8")
    )
    comparison = json.loads(
        (comparison_run / "reports" / "summary.json").read_text(encoding="utf-8")
    )
    config_hash = hash_text(
        baseline_config.read_text(encoding="utf-8")
        + comparison_config.read_text(encoding="utf-8")
    )
    datasets = FileDatasetRepository(project_root / "data")
    registry = RunRegistry(project_root / "runs")
    paths, manifest = registry.create(
        experiment_id="framework-comparison-v1",
        framework="suite",
        provider="mock",
        model="mock-llm",
        config_path=Path("configs/experiments/suite_v1.json"),
        config_hash=config_hash,
        dataset_name="controlled_synthetic",
        dataset_version="v1",
        dataset_hash=datasets.content_hash("controlled_synthetic", "v1"),
        seed=42,
        repetition_id=0,
    )
    try:
        result = CompareFrameworks().execute(baseline, comparison)
        paths.log.write_text(
            f"Compared {baseline_run.name} with {comparison_run.name}.\n",
            encoding="utf-8",
        )
        write_json_atomic(paths.summary, result)
        write_csv(
            paths.tables / "framework_comparison.csv",
            (
                "configuration",
                "baseline_framework",
                "comparison_framework",
                "baseline_mean_total_tokens",
                "comparison_mean_total_tokens",
                "mean_total_tokens_delta",
                "baseline_mean_redundancy_ratio",
                "comparison_mean_redundancy_ratio",
                "mean_redundancy_ratio_delta",
                "baseline_task_success_rate",
                "comparison_task_success_rate",
                "task_success_rate_delta",
            ),
            result["rows"],
        )
        registry.complete(paths, manifest)
        return paths.root
    except Exception as error:
        registry.fail(paths, manifest, f"{type(error).__name__}: {error}")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
