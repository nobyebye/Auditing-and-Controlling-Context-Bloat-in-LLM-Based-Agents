"""Deterministic, versioned evidence rules for the four thesis RQs."""

from __future__ import annotations

from typing import Any, Mapping

from context_auditor.domain.models import SCHEMA_VERSION


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
            "schema_version": summary.get("schema_version", SCHEMA_VERSION),
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
        macro_f1 = values.get("task_macro_binary_f1")
        localization = values.get("localization_accuracy")
        macro_ci = values.get("task_macro_binary_f1_ci95")
        localization_ci = values.get("localization_accuracy_ci95")
        reference_type = values.get("reference_type")
        if macro_f1 is None or localization is None:
            return evidence(
                "Insufficient data",
                "An independent detection reference is unavailable.",
                values,
            )
        if reference_type != "human_reference":
            return evidence(
                "Controlled-only",
                "The result measures consistency with injected perturbations and is "
                "not independent detector validation.",
                values,
            )
        macro_low, macro_high = macro_ci or (macro_f1, macro_f1)
        localization_low, localization_high = localization_ci or (
            localization,
            localization,
        )
        if (
            macro_low >= rule["minimum_macro_f1"]
            and localization_low >= rule["minimum_localization_accuracy"]
        ):
            status = "Supported by independent labels"
        elif (
            macro_high < rule["minimum_macro_f1"]
            or localization_high < rule["minimum_localization_accuracy"]
        ):
            status = "Not supported by independent labels"
        else:
            status = "Inconclusive"
        text = (
            f"Task-macro binary F1 is {macro_f1:.3f} and localization accuracy is "
            f"{localization:.3f}; status uses task-cluster bootstrap intervals."
        )
        return evidence(status, text, values)

    @staticmethod
    def _rq2(values: Mapping[str, Any], rule: Mapping[str, Any]) -> dict:
        rho = values.get("spearman_rho")
        rho_ci = values.get("spearman_rho_ci95")
        reference_type = values.get("reference_type")
        if rho is None:
            return evidence("Insufficient data", "Measurement pairs are unavailable.", values)
        if reference_type != "human_reference":
            return evidence(
                "Controlled-only",
                "The correlation uses injected perturbations and is reported as "
                "pipeline consistency rather than independent measurement validity.",
                values,
            )
        rho_low, rho_high = rho_ci or (rho, rho)
        if rho_low >= rule["minimum_spearman_rho"]:
            status = "Supported by independent labels"
        elif rho_high < rule["minimum_spearman_rho"]:
            status = "Not supported by independent labels"
        else:
            status = "Inconclusive"
        return evidence(
            status,
            f"Measured and human-reference bloat have Spearman rho {rho:.3f}; "
            "status uses the task-cluster bootstrap interval.",
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
            "Descriptive evidence",
            f"Within this study sample, the largest observed mean bloat ratio is "
            f"associated with {leading_source}; this is not a universal source ranking.",
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
        degradation = success_ci[1] < 0
        if reduction_supported and noninferior:
            status = "Token reduction with non-inferior utility"
        elif reduction_supported and degradation:
            status = "Token reduction with degradation risk"
        elif reduction_ci[1] <= rule["minimum_token_reduction"]:
            status = "No established token reduction"
        else:
            status = "Mixed evidence"
        return evidence(
            status,
            "Token reduction and task utility are reported as separate outcomes; "
            "non-inferiority is not inferred from token savings.",
            {
                **values,
                "noninferiority_sensitivity_margins": rule.get(
                    "sensitivity_margins",
                    [-0.02, -0.05, -0.10],
                ),
            },
        )


def evidence(status: str, conclusion: str, metrics: Mapping[str, Any]) -> dict:
    return {
        "status": status,
        "conclusion": conclusion,
        "metrics": dict(metrics),
    }
