"""Independent counterfactual and mitigation evidence for Study C."""

from __future__ import annotations

import json
import math
import warnings
from collections import defaultdict
from pathlib import Path
from statistics import mean

from context_auditor.adapters.storage.serialization import write_json_atomic
from context_auditor.application.evaluation import bootstrap_mean_interval
from context_auditor.application.external_annotations import write_csv
from context_auditor.application.outcome_annotations import (
    load_outcome_consensus,
    load_trace_file,
)
from context_auditor.domain.models import AuditTrace, SCHEMA_VERSION


def build_study_c_evidence(
    traces_path: str | Path,
    outcome_adjudication_path: str | Path,
    outcome_answer_key_path: str | Path,
    output_dir: str | Path,
) -> Path:
    traces = load_trace_file(Path(traces_path))
    human_outcomes = load_outcome_consensus(
        outcome_adjudication_path,
        outcome_answer_key_path,
    )
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"Study C evidence output exists: {destination}")
    destination.mkdir(parents=True)
    selected = [
        trace
        for trace in traces
        if trace.evidence_tier in {"counterfactual", "mitigation"}
    ]
    if set(human_outcomes) != {trace.trace_id for trace in selected}:
        raise ValueError(
            "Human outcomes must cover all Study C counterfactual and "
            "mitigation traces"
        )
    counterfactual = evaluate_counterfactuals(traces, human_outcomes)
    mitigation = evaluate_mitigation_arms(traces, human_outcomes)
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "study": "C",
        "analysis_unit": "task_id",
        "counterfactual": counterfactual,
        "mitigation": mitigation,
        "automatic_scorer_validation": scorer_validation(
            selected,
            human_outcomes,
        ),
        "rq4_interpretation": interpret_rq4(mitigation),
    }
    write_json_atomic(destination / "study_c_evidence.json", evidence)
    rows = [
        {
            "arm": arm,
            **values,
        }
        for arm, values in mitigation["by_arm"].items()
    ]
    write_csv(
        destination / "mitigation_by_arm.csv",
        tuple(rows[0]),
        rows,
    )
    return destination


def evaluate_counterfactuals(
    traces: list[AuditTrace],
    human_outcomes: dict[str, bool],
) -> dict:
    selected = [
        trace for trace in traces if trace.evidence_tier == "counterfactual"
    ]
    groups: dict[str, dict[int, dict[str, AuditTrace]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for trace in selected:
        if not trace.parent_trace_id:
            raise ValueError("Counterfactual trace lacks parent_trace_id")
        groups[trace.parent_trace_id][trace.repetition_id][
            trace.configuration
        ] = trace
    removable = 0
    candidate_preserved = 0
    necessary_degraded = 0
    complete = 0
    for repetitions in groups.values():
        if len(repetitions) != 2:
            continue
        required = {
            "counterfactual_baseline",
            "remove_human_candidate",
            "remove_matched_keep",
        }
        if any(set(arms) != required for arms in repetitions.values()):
            continue
        complete += 1
        baseline_ok = all(
            human_outcomes[arms["counterfactual_baseline"].trace_id]
            for arms in repetitions.values()
        )
        candidate_ok = baseline_ok and all(
            human_outcomes[arms["remove_human_candidate"].trace_id]
            for arms in repetitions.values()
        )
        necessary_hurt = baseline_ok and any(
            not human_outcomes[arms["remove_matched_keep"].trace_id]
            for arms in repetitions.values()
        )
        candidate_preserved += int(candidate_ok)
        removable += int(candidate_ok)
        necessary_degraded += int(necessary_hurt)
    return {
        "context_count": len(groups),
        "complete_context_count": complete,
        "counterfactually_removable_count": removable,
        "candidate_preservation_rate": (
            candidate_preserved / complete if complete else None
        ),
        "matched_keep_degradation_rate": (
            necessary_degraded / complete if complete else None
        ),
        "definition": (
            "A candidate is removable only when both human-adjudicated "
            "baseline replicates succeed and both candidate-removal "
            "replicates preserve success."
        ),
        "scope": "conditional_on_adjudicated_remove_candidates",
    }


def evaluate_mitigation_arms(
    traces: list[AuditTrace],
    human_outcomes: dict[str, bool],
) -> dict:
    selected = [
        trace for trace in traces if trace.evidence_tier == "mitigation"
    ]
    keyed: dict[tuple[str, str], dict[str, AuditTrace]] = defaultdict(dict)
    for trace in selected:
        keyed[(trace.task_id, trace.framework)][trace.configuration] = trace
    required = {
        "unmodified",
        "provenance_aware",
        "llmlingua2_budget_matched",
    }
    incomplete = [key for key, arms in keyed.items() if set(arms) != required]
    if incomplete:
        raise ValueError(f"Incomplete mitigation pairs: {incomplete[:5]}")
    by_arm = {}
    for arm in sorted(required):
        arm_traces = [arms[arm] for arms in keyed.values()]
        costs = [
            float(trace.provider_usage.cost_usd)
            for trace in arm_traces
            if trace.provider_usage.cost_usd is not None
        ]
        latencies = [
            float(trace.latency_ms)
            for trace in arm_traces
            if trace.latency_ms is not None
        ]
        by_arm[arm] = {
            "trace_count": len(arm_traces),
            "task_count": len({trace.task_id for trace in arm_traces}),
            "mean_context_tokens": mean(
                float(trace.metrics.get("total_tokens", 0))
                for trace in arm_traces
            ),
            "mean_provider_input_tokens": mean(
                float(trace.provider_usage.input_tokens or 0)
                for trace in arm_traces
            ),
            "mean_cost_usd": mean(costs) if costs else None,
            "cost_observation_count": len(costs),
            "mean_latency_ms": mean(latencies) if latencies else None,
            "latency_observation_count": len(latencies),
            "automatic_success_rate": mean(
                float(bool(trace.task_success)) for trace in arm_traces
            ),
            "human_success_rate": mean(
                float(human_outcomes[trace.trace_id]) for trace in arm_traces
            ),
        }
    comparisons = {
        arm: paired_arm_comparison(
            keyed,
            human_outcomes,
            arm,
        )
        for arm in ("provenance_aware", "llmlingua2_budget_matched")
    }
    return {
        "pair_count": len(keyed),
        "independent_task_count": len({task for task, _ in keyed}),
        "by_arm": by_arm,
        "versus_unmodified": comparisons,
    }


def paired_arm_comparison(
    keyed: dict[tuple[str, str], dict[str, AuditTrace]],
    human_outcomes: dict[str, bool],
    arm: str,
) -> dict:
    by_task: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    raw_success = []
    for (task_id, _framework), arms in keyed.items():
        baseline = arms["unmodified"]
        treated = arms[arm]
        before_tokens = float(baseline.metrics.get("total_tokens", 0))
        after_tokens = float(treated.metrics.get("total_tokens", 0))
        reduction = before_tokens - after_tokens
        ratio = reduction / before_tokens if before_tokens else 0.0
        human_difference = float(human_outcomes[treated.trace_id]) - float(
            human_outcomes[baseline.trace_id]
        )
        automatic_difference = float(bool(treated.task_success)) - float(
            bool(baseline.task_success)
        )
        values = by_task[task_id]
        values["token_reduction"].append(reduction)
        values["token_ratio"].append(ratio)
        values["human_success"].append(human_difference)
        values["automatic_success"].append(automatic_difference)
        if (
            baseline.provider_usage.cost_usd is not None
            and treated.provider_usage.cost_usd is not None
        ):
            values["cost"].append(
                float(baseline.provider_usage.cost_usd)
                - float(treated.provider_usage.cost_usd)
            )
        if baseline.latency_ms is not None and treated.latency_ms is not None:
            values["latency"].append(
                float(baseline.latency_ms)
                - float(treated.latency_ms)
            )
        raw_success.extend(
            [
                (task_id, 0, int(human_outcomes[baseline.trace_id])),
                (task_id, 1, int(human_outcomes[treated.trace_id])),
            ]
        )
    task_values = {
        name: [
            mean(values[name])
            for values in by_task.values()
            if values.get(name)
        ]
        for name in (
            "token_reduction",
            "token_ratio",
            "human_success",
            "automatic_success",
            "cost",
            "latency",
        )
    }
    human_ci = bootstrap_mean_interval(task_values["human_success"])
    return {
        "task_count": len(by_task),
        "mean_token_reduction": mean(task_values["token_reduction"]),
        "token_reduction_ci95": bootstrap_mean_interval(
            task_values["token_reduction"]
        ),
        "mean_token_reduction_ratio": mean(task_values["token_ratio"]),
        "token_reduction_ratio_ci95": bootstrap_mean_interval(
            task_values["token_ratio"]
        ),
        "mean_human_success_difference": mean(task_values["human_success"]),
        "human_success_difference_ci95": human_ci,
        "mean_automatic_success_difference": mean(
            task_values["automatic_success"]
        ),
        "automatic_success_difference_ci95": bootstrap_mean_interval(
            task_values["automatic_success"]
        ),
        "mean_cost_reduction_usd": optional_mean(task_values["cost"]),
        "cost_reduction_ci95": bootstrap_mean_interval(task_values["cost"]),
        "cost_task_count": len(task_values["cost"]),
        "mean_latency_reduction_ms": optional_mean(task_values["latency"]),
        "latency_reduction_ci95": bootstrap_mean_interval(
            task_values["latency"]
        ),
        "latency_task_count": len(task_values["latency"]),
        "noninferiority_sensitivity": {
            str(margin): (
                human_ci is not None and human_ci[0] >= margin
            )
            for margin in (-0.02, -0.05, -0.10)
        },
        "task_clustered_logistic_gee": fit_task_clustered_gee(raw_success),
    }


def scorer_validation(
    traces: list[AuditTrace],
    human_outcomes: dict[str, bool],
) -> dict:
    def summarize(items: list[AuditTrace]) -> dict:
        tp = sum(
            bool(trace.task_success) and human_outcomes[trace.trace_id]
            for trace in items
        )
        tn = sum(
            not bool(trace.task_success) and not human_outcomes[trace.trace_id]
            for trace in items
        )
        fp = sum(
            bool(trace.task_success) and not human_outcomes[trace.trace_id]
            for trace in items
        )
        fn = sum(
            not bool(trace.task_success) and human_outcomes[trace.trace_id]
            for trace in items
        )
        total = tp + tn + fp + fn
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        specificity = tn / (tn + fp) if tn + fp else 0.0
        accuracy = (tp + tn) / total if total else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        observed = accuracy or 0.0
        automatic_positive = (tp + fp) / total if total else 0.0
        human_positive = (tp + fn) / total if total else 0.0
        chance = (
            automatic_positive * human_positive
            + (1 - automatic_positive) * (1 - human_positive)
        )
        kappa = (
            (observed - chance) / (1 - chance)
            if total and chance < 1
            else None
        )
        return {
            "trace_count": total,
            "true_positive": tp,
            "true_negative": tn,
            "false_positive": fp,
            "false_negative": fn,
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "specificity": specificity,
            "f1": f1,
            "cohen_kappa": kappa,
        }

    workflows = sorted({trace.workflow_family for trace in traces})
    arms = sorted({trace.configuration for trace in traces})
    return {
        "overall": summarize(traces),
        "by_workflow": {
            workflow: summarize(
                [trace for trace in traces if trace.workflow_family == workflow]
            )
            for workflow in workflows
        },
        "by_arm": {
            arm: summarize(
                [trace for trace in traces if trace.configuration == arm]
            )
            for arm in arms
        },
    }


def fit_task_clustered_gee(
    observations: list[tuple[str, int, int]],
) -> dict:
    try:
        import statsmodels.api as sm
    except ImportError:
        return {
            "status": "not_available",
            "reason": "Install the optional statistics dependency.",
        }
    endog = [success for _task, _treated, success in observations]
    exog = [[1.0, float(treated)] for _task, treated, _success in observations]
    groups = [task for task, _treated, _success in observations]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = sm.GEE(
                endog,
                exog,
                groups=groups,
                family=sm.families.Binomial(),
            ).fit()
            values = [
                float(result.params[1]),
                float(result.bse[1]),
                float(result.pvalues[1]),
                float(result.conf_int()[1][0]),
                float(result.conf_int()[1][1]),
            ]
    except Exception as error:
        return {"status": "failed", "reason": str(error)}
    if not all(math.isfinite(value) for value in values):
        return {
            "status": "not_estimable",
            "reason": "The fitted contrast has no finite variance estimate.",
        }
    return {
        "status": "completed",
        "treated_log_odds": values[0],
        "standard_error": values[1],
        "p_value": values[2],
        "confidence_interval_95": values[3:],
    }


def interpret_rq4(mitigation: dict) -> dict:
    provenance = mitigation["versus_unmodified"]["provenance_aware"]
    reduction = provenance["mean_token_reduction_ratio"]
    ci = provenance["human_success_difference_ci95"]
    if reduction <= 0:
        status = "No token reduction"
    elif ci is None:
        status = "Insufficient human evidence"
    elif ci[0] >= -0.05:
        status = "Non-inferiority established at -5 percentage points"
    else:
        status = "Token reduction with performance degradation risk"
    return {
        "status": status,
        "token_reduction_ratio": reduction,
        "human_success_difference_ci95": ci,
        "noninferiority_margin": -0.05,
    }


def optional_mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def trace_score(trace: AuditTrace) -> float:
    if trace.scoring is not None:
        return float(trace.scoring.score)
    return float(bool(trace.task_success))
