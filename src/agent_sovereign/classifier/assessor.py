"""Sovereignty assessor.

Provides SovereigntyAssessor, the top-level classifier that combines data
sensitivity, regulatory requirements, geographic constraints, and rule engine
output into a single SovereigntyAssessment.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

from agent_sovereign.classifier.levels import (
    SovereigntyLevel,
    get_capability_requirements,
    get_level_description,
)
from agent_sovereign.classifier.regulatory import RegulatoryMapper
from agent_sovereign.classifier.rules import ClassificationRules
from agent_sovereign.classifier.sensitivity import DATA_SENSITIVITY, DataSensitivityDetector

# Geographic region → minimum sovereignty level score.
_GEOGRAPHY_MINIMUMS: dict[str, int] = {
    "EU": 6,
    "EEA": 6,
    "DE": 6,
    "FR": 6,
    "UK": 4,
    "US_FEDERAL": 4,
    "US_DOD": 5,
    "CN": 6,
    "RU": 6,
    "IN": 3,
    "AU": 3,
    "CA": 3,
    "JP": 3,
    "SG": 3,
    "US": 2,
    "GLOBAL": 1,
}

# Deployment template names keyed by SovereigntyLevel value
_DEPLOYMENT_TEMPLATE_NAMES: dict[int, str] = {
    1: "l1_cloud",
    2: "l2_cloud_fallback",
    3: "l3_hybrid",
    4: "l4_local_augmented",
    5: "l5_fully_local",
    6: "l6_classified",
    7: "l7_airgapped",
}


@dataclass
class SovereigntyAssessment:
    """Result of a sovereignty level assessment.

    Attributes
    ----------
    level:
        The recommended minimum sovereignty level.
    score:
        The numeric score (1–7) that was determined.
    justification:
        Human-readable explanation of why this level was chosen.
    data_sensitivity:
        The highest data sensitivity score from the provided data types.
    regulatory_drivers:
        Map of regulation names to the levels they require.
    deployment_template:
        Name of the recommended deployment template (without .yaml extension).
    warnings:
        List of advisory warnings (e.g. conflicting regulations, near-threshold).
    capability_requirements:
        Capability requirements dict for the recommended level.
    """

    level: SovereigntyLevel
    score: int
    justification: str
    data_sensitivity: int
    regulatory_drivers: dict[str, SovereigntyLevel]
    deployment_template: str
    warnings: list[str] = field(default_factory=list)
    capability_requirements: dict[str, str] = field(default_factory=dict)


class SovereigntyAssessor:
    """Assess the minimum sovereignty level for a workload.

    Combines data sensitivity scores, regulatory minimums, geographic
    constraints, organisational minimums, and the rule engine to determine
    the strictest (highest) required sovereignty level.

    Parameters
    ----------
    rules_source:
        Optional path or YAML string for custom classification rules.
        Defaults to built-in rules.
    org_minimum:
        Organisational baseline level. Assessments will never fall below this.
    additional_geo_minimums:
        Optional overrides for geography-to-level mappings.
    """

    def __init__(
        self,
        rules_source: Union[str, Path, None] = None,
        org_minimum: SovereigntyLevel = SovereigntyLevel.L1_CLOUD,
        additional_geo_minimums: dict[str, int] | None = None,
    ) -> None:
        self._rules = ClassificationRules(rules_source)
        self._reg_mapper = RegulatoryMapper()
        self._sensitivity_detector = DataSensitivityDetector()
        self._org_minimum = org_minimum
        self._geo_minimums: dict[str, int] = dict(_GEOGRAPHY_MINIMUMS)
        if additional_geo_minimums:
            self._geo_minimums.update(additional_geo_minimums)

    def assess(
        self,
        data_types: list[str],
        regulations: list[str],
        geography: str | None = None,
        org_minimum: SovereigntyLevel | None = None,
    ) -> SovereigntyAssessment:
        """Assess the required sovereignty level for a workload.

        Takes the maximum of all applicable drivers:
        1. Data sensitivity scores from DATA_SENSITIVITY.
        2. Regulatory minimums from REGULATORY_MINIMUMS.
        3. Geographic requirement from geography mapping.
        4. Organisational minimum.
        5. Rule-engine matches from ClassificationRules.

        Parameters
        ----------
        data_types:
            List of data type keys (e.g. "phi", "financial_data").
        regulations:
            List of applicable regulation identifiers (e.g. "HIPAA", "GDPR").
        geography:
            ISO or region code for the deployment geography (e.g. "EU", "US").
        org_minimum:
            Per-call organisational minimum override. Falls back to instance
            default if not provided.

        Returns
        -------
        SovereigntyAssessment
            Full assessment with level, justification, and driver breakdown.
        """
        effective_org_min = org_minimum if org_minimum is not None else self._org_minimum
        justification_parts: list[str] = []
        warnings: list[str] = []

        # 1. Data sensitivity
        data_score = self._sensitivity_detector.score_data_types(data_types)
        if data_score > 1:
            justification_parts.append(
                f"Data sensitivity: {data_score} "
                f"(from types: {', '.join(t for t in data_types if DATA_SENSITIVITY.get(t, 1) >= data_score)})"
            )

        # 2. Regulatory minimums
        reg_drivers = self._reg_mapper.drivers_for(regulations)
        reg_score = max((level.value for level in reg_drivers.values()), default=1)
        if reg_score > 1:
            top_regs = [
                reg for reg, level in reg_drivers.items() if level.value == reg_score
            ]
            justification_parts.append(
                f"Regulatory requirement: {reg_score} "
                f"(driven by: {', '.join(top_regs)})"
            )

        unknown_regs = [reg for reg in regulations if reg not in reg_drivers]
        if unknown_regs:
            warnings.append(
                f"Unrecognised regulations ignored: {', '.join(unknown_regs)}. "
                "Add them via RegulatoryMapper additional_minimums."
            )

        # 3. Geographic requirement
        geo_score = 1
        if geography:
            geo_score = self._geo_minimums.get(geography, 1)
            if geo_score > 1:
                justification_parts.append(
                    f"Geographic requirement: {geo_score} (geography: {geography})"
                )
            elif geography not in self._geo_minimums:
                warnings.append(
                    f"Geography {geography!r} is not in the known geography map; "
                    "defaulting to L1 for geographic driver."
                )

        # 4. Organisational minimum
        org_score = effective_org_min.value
        if org_score > 1:
            justification_parts.append(
                f"Organisational minimum: {org_score}"
            )

        # 5. Rule engine
        rule_result = self._rules.evaluate(data_types, regulations, geography)
        rule_score = rule_result.rule_driven_level.value
        if rule_result.matched_rules:
            justification_parts.extend(rule_result.rule_justifications)

        # Final score: maximum of all drivers
        final_score = max(data_score, reg_score, geo_score, org_score, rule_score)
        final_score = max(1, min(7, final_score))
        final_level = SovereigntyLevel(final_score)

        # Build justification
        driver_scores = {
            "data_sensitivity": data_score,
            "regulatory": reg_score,
            "geographic": geo_score,
            "organisational_minimum": org_score,
            "rule_engine": rule_score,
        }
        winning_driver = max(driver_scores, key=lambda k: driver_scores[k])

        if justification_parts:
            justification = (
                f"Level {final_score} ({final_level.name}) required. "
                f"Determining driver: {winning_driver}. "
                + " | ".join(justification_parts)
            )
        else:
            justification = (
                f"Level {final_score} ({final_level.name}): "
                f"No sensitive data, regulations, or geographic constraints identified. "
                f"Defaulting to baseline."
            )

        # Near-threshold warnings
        if final_score == 6 and "GDPR" in regulations:
            warnings.append(
                "GDPR drives this to L6. Verify data residency contracts "
                "and DPA agreements are in place."
            )
        if final_score == 7:
            warnings.append(
                "L7 (air-gap) requires physical media for all model updates "
                "and prevents any connectivity-based monitoring."
            )

        deployment_template = _DEPLOYMENT_TEMPLATE_NAMES.get(final_score, "l1_cloud")

        return SovereigntyAssessment(
            level=final_level,
            score=final_score,
            justification=justification,
            data_sensitivity=data_score,
            regulatory_drivers=reg_drivers,
            deployment_template=deployment_template,
            warnings=warnings,
            capability_requirements=get_capability_requirements(final_level),
        )

    def describe_level(self, level: SovereigntyLevel) -> str:
        """Return a human-readable description of a sovereignty level.

        Parameters
        ----------
        level:
            The level to describe.

        Returns
        -------
        str
            Prose description of the level.
        """
        return get_level_description(level)


__all__ = [
    "SovereigntyAssessment",
    "SovereigntyAssessor",
]
