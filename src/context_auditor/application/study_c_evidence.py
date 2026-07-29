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
    rateable_outcome,
)
from context_auditor.domain.models import AuditTrace, SCHEMA_VERSION

STUDY_C_ARMS = frozenset(
    {
        "counterfactual_baseline",
        "remove_human_candidate",
        "remove_matched_keep",
        "unmodified",
        "provenance_aware",
        "llmlingua2_budget_matched",
    }
)


def build_study_c_evidence(
    traces_path: str | Path,
    ledger_path: str | Path,
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
    rateable_ids = {
        trace.trace_id for trace in selected if rateable_outcome(trace)
    }
    if set(human_outcomes) != rateable_ids:
        raise ValueError(
            "Human outcomes must cover exactly the rateable Study C outputs"
        )
    all_outcomes = {
        trace.trace_id: (
            human_outcomes[trace.trace_id]
            if trace.trace_id in human_outcomes
            else False
        )
        for trace in selected
    }
    execution_rows = build_itt_execution_table(
        ledger_path,
        traces,
        human_outcomes,
    )
    counterfactual = evaluate_counterfactuals(traces, all_outcomes)
    mitigation = evaluate_mitigation_arms(
        traces,
        all_outcomes,
        execution_rows=execution_rows,
    )
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "study": "C",
        "analysis_unit": "task_id",
        "itt_execution": summarize_itt_execution(execution_rows),
        "counterfactual": counterfactual,
        "mitigation": mitigation,
        "automatic_scorer_validation": scorer_validation(
            selected,
            all_outcomes,
        ),
        "rq4_interpretation": interpret_rq4(mitigation),
    }
    write_json_atomic(destination / "study_c_evidence.json", evidence)
    write_csv(
        destination / "itt_execution.csv",
        tuple(execution_rows[0]),
        execution_rows,
    )
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


def build_itt_execution_table(
    ledger_path: str | Path,
    traces: list[AuditTrace],
    human_outcomes: dict[str, bool],
) -> list[dict]:
    ledger = Path(ledger_path)
    if not ledger.is_file():
        raise FileNotFoundError(f"Study C call ledger is missing: {ledger}")
    records = [
        json.loads(line)
        for line in ledger.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    reservations = [
        item
        for item in records
        if item.get("event") == "reserved"
        and item.get("arm") in STUDY_C_ARMS
    ]
    outcomes = {
        str(item["call_id"]): item
        for item in records
        if item.get("event") in {"completed", "failed"}
    }
    traces_by_cell: dict[str, AuditTrace] = {}
    for trace in traces:
        if trace.evidence_tier not in {"counterfactual", "mitigation"}:
            continue
        if not trace.request_envelope:
            continue
        cell_id = str(trace.request_envelope.metadata.get("cell_id", ""))
        if not cell_id:
            continue
        if cell_id in traces_by_cell:
            raise ValueError(f"Multiple Study C traces share cell_id={cell_id}")
        traces_by_cell[cell_id] = trace

    rows = []
    for reservation in sorted(
        reservations,
        key=lambda item: int(item["call_index"]),
    ):
        call_id = str(reservation["call_id"])
        terminal = outcomes.get(call_id)
        cell_id = str(reservation.get("cell_id", ""))
        trace = traces_by_cell.get(cell_id)
        rateable = bool(trace and rateable_outcome(trace))
        if rateable and trace.trace_id not in human_outcomes:
            raise ValueError(
                "A rateable Study C output lacks adjudicated human scoring: "
                + trace.trace_id
            )
        failure_reason = itt_failure_reason(terminal, trace)
        rows.append(
            {
                "call_id": call_id,
                "call_index": int(reservation["call_index"]),
                "cell_id": cell_id,
                "task_id": str(reservation.get("task_id", "")),
                "framework": str(reservation.get("framework", "")),
                "arm": str(reservation.get("arm", "")),
                "invocation_index": int(
                    reservation.get("invocation_index", 0)
                ),
                "retry_of": str(reservation.get("retry_of") or ""),
                "main_itt": not bool(reservation.get("retry_of")),
                "ledger_status": (
                    str(terminal.get("status", ""))
                    if terminal
                    else "missing_terminal_event"
                ),
                "trace_id": trace.trace_id if trace else "",
                "rateable_output": rateable,
                "human_scored": bool(
                    trace and trace.trace_id in human_outcomes
                ),
                "human_task_success": bool(
                    trace
                    and trace.trace_id in human_outcomes
                    and human_outcomes[trace.trace_id]
                ),
                "automatic_task_success": bool(
                    trace and trace.task_success
                ),
                "itt_task_success": bool(
                    trace
                    and trace.trace_id in human_outcomes
                    and human_outcomes[trace.trace_id]
                    and not failure_reason
                ),
                "failure_reason": failure_reason,
            }
        )
    if not rows:
        raise ValueError("The ledger contains no dispatched Study C requests")
    return rows


def itt_failure_reason(
    terminal: dict | None,
    trace: AuditTrace | None,
) -> str:
    if terminal is None:
        return "missing_terminal_ledger_event"
    if terminal.get("event") == "failed":
        return str(terminal.get("error_type") or "provider_error")
    if trace is None:
        return "missing_trace_after_dispatch"
    dispatch_error = str(trace.intervention.get("dispatch_error_type") or "")
    if dispatch_error:
        return dispatch_error
    if not (trace.task_output or "").strip():
        return "empty_output"
    if trace.scoring is None:
        return "missing_scoring_record"
    method = trace.scoring.method.lower()
    details_reason = str(trace.scoring.details.get("failure_reason", ""))
    if details_reason:
        return details_reason
    if "tool_call" in method:
        return "tool_call_violation"
    if "parse" in method and not trace.scoring.success:
        return "parse_failure"
    return ""


def summarize_itt_execution(rows: list[dict]) -> dict:
    main = [row for row in rows if row["main_itt"]]
    failures: dict[str, int] = defaultdict(int)
    for row in main:
        if row["failure_reason"]:
            failures[str(row["failure_reason"])] += 1
    return {
        "all_dispatched_request_count": len(rows),
        "primary_request_count": len(main),
        "manual_retry_count": len(rows) - len(main),
        "rateable_output_count": sum(row["rateable_output"] for row in main),
        "human_scored_output_count": sum(row["human_scored"] for row in main),
        "itt_failure_count": sum(not row["itt_task_success"] for row in main),
        "failure_reasons": dict(sorted(failures.items())),
        "definition": (
            "Every dispatched primary request is retained. Missing or "
            "unrateable outputs are coded as task failure."
        ),
    }


def evaluate_mitigation_itt(execution_rows: list[dict]) -> dict:
    required = {
        "unmodified",
        "provenance_aware",
        "llmlingua2_budget_matched",
    }
    selected = [
        row
        for row in execution_rows
        if row["main_itt"] and row["arm"] in required
    ]
    keyed: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    for row in selected:
        key = (str(row["task_id"]), str(row["framework"]))
        if row["arm"] in keyed[key]:
            raise ValueError(f"Duplicate primary mitigation dispatch: {key}")
        keyed[key][str(row["arm"])] = row
    complete = {
        key: arms for key, arms in keyed.items() if set(arms) == required
    }
    incomplete = [key for key, arms in keyed.items() if set(arms) != required]
    by_arm = {
        arm: {
            "request_count": sum(arm in arms for arms in keyed.values()),
            "itt_human_success_rate": optional_mean(
                [
                    float(arms[arm]["itt_task_success"])
                    for arms in keyed.values()
                    if arm in arms
                ]
            ),
        }
        for arm in sorted(required)
    }
    comparisons = {}
    for arm in ("provenance_aware", "llmlingua2_budget_matched"):
        by_task: dict[str, list[float]] = defaultdict(list)
        gee_rows = []
        for (task_id, _framework), arms in complete.items():
            baseline = int(arms["unmodified"]["itt_task_success"])
            treated = int(arms[arm]["itt_task_success"])
            by_task[task_id].append(float(treated - baseline))
            gee_rows.extend(
                [(task_id, 0, baseline), (task_id, 1, treated)]
            )
        task_differences = [
            mean(values) for values in by_task.values()
        ]
        confidence_interval = bootstrap_mean_interval(task_differences)
        comparisons[arm] = {
            "independent_task_count": len(by_task),
            "mean_human_success_difference": (
                mean(task_differences) if task_differences else None
            ),
            "human_success_difference_ci95": confidence_interval,
            "noninferiority_sensitivity": {
                str(margin): (
                    confidence_interval is not None
                    and confidence_interval[0] >= margin
                )
                for margin in (-0.02, -0.05, -0.10)
            },
            "task_clustered_logistic_gee": fit_task_clustered_gee(
                gee_rows
            ),
        }
    return {
        "primary_dispatch_count": len(selected),
        "complete_framework_task_cell_count": len(complete),
        "incomplete_framework_task_cell_count": len(incomplete),
        "independent_task_count": len(
            {task_id for task_id, _framework in keyed}
        ),
        "by_arm": by_arm,
        "versus_unmodified": comparisons,
    }


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
    *,
    execution_rows: list[dict] | None = None,
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
    keyed = {
        key: arms for key, arms in keyed.items() if set(arms) == required
    }
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
            "mean_context_tokens": optional_mean([
                float(trace.metrics.get("total_tokens", 0))
                for trace in arm_traces
            ]),
            "mean_provider_input_tokens": optional_mean([
                float(trace.provider_usage.input_tokens or 0)
                for trace in arm_traces
            ]),
            "mean_cost_usd": mean(costs) if costs else None,
            "cost_observation_count": len(costs),
            "mean_latency_ms": mean(latencies) if latencies else None,
            "latency_observation_count": len(latencies),
            "automatic_success_rate": optional_mean([
                float(bool(trace.task_success)) for trace in arm_traces
            ]),
            "human_success_rate": optional_mean([
                float(human_outcomes[trace.trace_id]) for trace in arm_traces
            ]),
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
        "incomplete_trace_pair_count": len(incomplete),
        "independent_task_count": len({task for task, _ in keyed}),
        "by_arm": by_arm,
        "versus_unmodified": comparisons,
        "itt": (
            evaluate_mitigation_itt(execution_rows)
            if execution_rows is not None
            else None
        ),
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
        "mean_token_reduction": optional_mean(task_values["token_reduction"]),
        "token_reduction_ci95": bootstrap_mean_interval(
            task_values["token_reduction"]
        ),
        "mean_token_reduction_ratio": optional_mean(task_values["token_ratio"]),
        "token_reduction_ratio_ci95": bootstrap_mean_interval(
            task_values["token_ratio"]
        ),
        "mean_human_success_difference": optional_mean(
            task_values["human_success"]
        ),
        "human_success_difference_ci95": human_ci,
        "mean_automatic_success_difference": optional_mean(
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
    itt = mitigation.get("itt") or {}
    itt_provenance = (
        itt.get("versus_unmodified", {}).get("provenance_aware", {})
    )
    ci = itt_provenance.get(
        "human_success_difference_ci95",
        provenance["human_success_difference_ci95"],
    )
    if reduction is None:
        status = "Insufficient paired token evidence"
    elif reduction <= 0:
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
        "task_success_analysis": "intention_to_treat_from_call_ledger",
    }


def optional_mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def trace_score(trace: AuditTrace) -> float:
    if trace.scoring is not None:
        return float(trace.scoring.score)
    return float(bool(trace.task_success))
