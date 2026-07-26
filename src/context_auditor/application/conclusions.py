"""Deterministic, versioned evidence rules for the four thesis RQs."""

from __future__ import annotations

from typing import Any, Mapping


class BuildRQEvidence:
    def execute(self, summary: Mapping[str, Any], rules: Mapping[str, Any]) -> dict:
        detection = summary.get("detection", {})
        measurement = summary.get("measurement", {})
        mitigation = summary.get("mitigation_effect", {})
        rq1 = self._rq1(detection, rules["rq1"])
        rq2 = self._rq2(measurement, rules["rq2"])
        rq3 = self._rq3(summary)
        rq4 = self._rq4(mitigation, rules["rq4"])
        return {
            "schema_version": summary.get("schema_version", "1.1.0"),
            "rule_version": rules["rule_version"],
            "research_questions": {
                "RQ1": rq1,
                "RQ2": rq2,
                "RQ3": rq3,
                "RQ4": rq4,
            },
        }

    @staticmethod
    def _rq1(values: Mapping[str, Any], rule: Mapping[str, Any]) -> dict:
        macro_f1 = values.get("macro_f1")
        localization = values.get("localization_accuracy")
        if macro_f1 is None or localization is None:
            return evidence("Insufficient data", "Detection ground truth is unavailable.", values)
        supported = (
            macro_f1 >= rule["minimum_macro_f1"]
            and localization >= rule["minimum_localization_accuracy"]
        )
        status = "Supported" if supported else "Not supported"
        text = (
            f"Detection macro-F1 is {macro_f1:.3f} and localization accuracy is "
            f"{localization:.3f}."
        )
        return evidence(status, text, values)

    @staticmethod
    def _rq2(values: Mapping[str, Any], rule: Mapping[str, Any]) -> dict:
        rho = values.get("spearman_rho")
        if rho is None:
            return evidence("Insufficient data", "Measurement pairs are unavailable.", values)
        status = "Supported" if rho >= rule["minimum_spearman_rho"] else "Not supported"
        return evidence(
            status,
            f"Measured bloat and ground truth have Spearman rho {rho:.3f}.",
            values,
        )

    @staticmethod
    def _rq3(summary: Mapping[str, Any]) -> dict:
        sources = summary.get("source_bloat", {})
        if not sources:
            return evidence("Insufficient data", "No source-level bloat data is available.", {})
        ordered = sorted(
            sources.items(),
            key=lambda item: item[1].get("mean_bloat_ratio", 0.0),
            reverse=True,
        )
        leading_source, leading = ordered[0]
        return evidence(
            "Supported",
            f"The largest observed mean bloat ratio is associated with {leading_source}.",
            {"ranking": [{"source": key, **value} for key, value in ordered]},
        )

    @staticmethod
    def _rq4(values: Mapping[str, Any], rule: Mapping[str, Any]) -> dict:
        reduction_ci = values.get("token_reduction_ci95")
        success_ci = values.get("task_success_difference_ci95")
        if not reduction_ci or not success_ci:
            return evidence("Insufficient data", "Paired mitigation results are unavailable.", values)
        reduction_supported = reduction_ci[0] > rule["minimum_token_reduction"]
        noninferior = success_ci[0] >= rule["noninferiority_margin"]
        if reduction_supported and noninferior:
            status = "Supported"
        elif reduction_ci[1] <= rule["minimum_token_reduction"] or success_ci[1] < rule["noninferiority_margin"]:
            status = "Not supported"
        else:
            status = "Inconclusive"
        return evidence(
            status,
            "Mitigation is judged by paired token reduction and the frozen task-success "
            "non-inferiority margin.",
            values,
        )


def evidence(status: str, conclusion: str, metrics: Mapping[str, Any]) -> dict:
    return {
        "status": status,
        "conclusion": conclusion,
        "metrics": dict(metrics),
    }
