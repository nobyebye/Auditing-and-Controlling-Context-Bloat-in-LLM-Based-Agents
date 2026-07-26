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
from context_auditor.application.reporting import write_csv
from context_auditor.application.study_bundle import ExportStudyBundle, validate_study_bundle
from context_auditor.domain.enums import PrivacyMode
from context_auditor.domain.models import CaptureRequest, Message
from context_auditor.domain.text import hash_text
from context_auditor.experiments import (
    RunExperiment,
    RunFormalExperiment,
    load_experiment_config,
)
from context_auditor.experiments.dataset_validation import validate_dataset


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
        response = DeepSeekProvider.from_environment(args.model).invoke(messages)
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
                "schema_version": "1.1.0",
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
