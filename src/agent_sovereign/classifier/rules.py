"""YAML-based classification rule engine.

Provides ClassificationRules — a rule engine that loads rules from YAML
configuration and maps combinations of data types and regulations to
sovereignty levels.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

import yaml

from agent_sovereign.classifier.levels import SovereigntyLevel
from agent_sovereign.classifier.regulatory import REGULATORY_MINIMUMS
from agent_sovereign.classifier.sensitivity import DATA_SENSITIVITY

# Default rules embedded as a YAML string so the engine works without
# an external file.
_DEFAULT_RULES_YAML = """\
version: "1.0"
rules:
  # Data-type-based overrides (supplement DATA_SENSITIVITY defaults)
  - id: phi_always_l5
    description: "PHI data always requires at least L5 when combined with any cloud deployment"
    data_types: ["phi"]
    minimum_level: 5

  - id: classified_airgap
    description: "Classified data always requires air-gap"
    data_types: ["classified", "itar_technical_data", "sci_compartmented"]
    minimum_level: 7

  - id: biometric_strict
    description: "Biometric and genetic data require fully local deployment"
    data_types: ["biometric_data", "genetic_data"]
    minimum_level: 5

  # Regulation-data-type combination rules
  - id: hipaa_phi_combination
    description: "HIPAA + PHI is stricter than either alone"
    data_types: ["phi", "medical_records"]
    regulations: ["HIPAA"]
    minimum_level: 4

  - id: gdpr_eu_combination
    description: "GDPR data in EU jurisdiction requires maximum classification"
    regulations: ["GDPR"]
    geographies: ["EU", "EEA"]
    minimum_level: 6

  - id: fedramp_financial
    description: "FedRAMP combined with financial data"
    data_types: ["financial_data"]
    regulations: ["FedRAMP_High", "FedRAMP_Moderate"]
    minimum_level: 5
"""


@dataclass
class ClassificationRule:
    """A single classification rule loaded from YAML."""

    rule_id: str
    description: str
    minimum_level: int
    data_types: list[str] = field(default_factory=list)
    regulations: list[str] = field(default_factory=list)
    geographies: list[str] = field(default_factory=list)

    def matches(
        self,
        data_types: list[str],
        regulations: list[str],
        geography: str | None,
    ) -> bool:
        """Return True if this rule fires for the given inputs.

        A rule fires when ALL specified conditions are met:
        - If data_types is non-empty: at least one listed type is in data_types.
        - If regulations is non-empty: at least one listed regulation is present.
        - If geographies is non-empty: geography matches one of the listed entries.

        Parameters
        ----------
        data_types:
            Data types present in the workload being classified.
        regulations:
            Applicable regulations.
        geography:
            ISO or region code of the deployment geography.

        Returns
        -------
        bool
            True if this rule applies.
        """
        if self.data_types and not any(dt in data_types for dt in self.data_types):
            return False
        if self.regulations and not any(reg in regulations for reg in self.regulations):
            return False
        if self.geographies and geography not in self.geographies:
            return False
        return True


@dataclass
class RuleMatchResult:
    """Result of evaluating all rules against an input."""

    matched_rules: list[ClassificationRule] = field(default_factory=list)
    """Rules that fired during evaluation."""

    rule_driven_level: SovereigntyLevel = SovereigntyLevel.L1_CLOUD
    """The highest level required by any matching rule."""

    rule_justifications: list[str] = field(default_factory=list)
    """Human-readable reasons from each matched rule."""


class ClassificationRules:
    """YAML-based rule engine for sovereignty classification.

    Loads rules from a YAML file or string, then evaluates them against
    data types, regulations, and geography to determine if any rules raise
    the required sovereignty level above the baseline.

    Parameters
    ----------
    yaml_source:
        Path to a YAML rules file, a YAML string, or None to use the
        built-in default rules.
    """

    def __init__(
        self,
        yaml_source: Union[str, Path, None] = None,
    ) -> None:
        self._rules: list[ClassificationRule] = []
        if yaml_source is None:
            self._load_from_string(_DEFAULT_RULES_YAML)
        elif isinstance(yaml_source, Path):
            self._load_from_file(yaml_source)
        else:
            # Could be a file path string or raw YAML — try file first
            path = Path(yaml_source)
            if path.exists():
                self._load_from_file(path)
            else:
                self._load_from_string(yaml_source)

    def _load_from_file(self, path: Path) -> None:
        content = path.read_text(encoding="utf-8")
        self._load_from_string(content)

    def _load_from_string(self, yaml_text: str) -> None:
        data = yaml.safe_load(io.StringIO(yaml_text))
        if not isinstance(data, dict) or "rules" not in data:
            raise ValueError("Rules YAML must have a top-level 'rules' key.")
        for rule_dict in data["rules"]:
            self._rules.append(
                ClassificationRule(
                    rule_id=rule_dict["id"],
                    description=rule_dict.get("description", ""),
                    minimum_level=int(rule_dict["minimum_level"]),
                    data_types=rule_dict.get("data_types", []),
                    regulations=rule_dict.get("regulations", []),
                    geographies=rule_dict.get("geographies", []),
                )
            )

    def evaluate(
        self,
        data_types: list[str],
        regulations: list[str],
        geography: str | None = None,
    ) -> RuleMatchResult:
        """Evaluate all rules and return the combined result.

        Parameters
        ----------
        data_types:
            Data types present in the workload.
        regulations:
            Applicable regulatory frameworks.
        geography:
            ISO/region code of the deployment geography (optional).

        Returns
        -------
        RuleMatchResult
            Which rules fired and the highest level they require.
        """
        matched: list[ClassificationRule] = []
        max_level = 1

        # Also apply base DATA_SENSITIVITY scores as implicit rules
        for data_type in data_types:
            score = DATA_SENSITIVITY.get(data_type, 1)
            if score > max_level:
                max_level = score

        # Apply base REGULATORY_MINIMUMS as implicit rules
        for regulation in regulations:
            score = REGULATORY_MINIMUMS.get(regulation, 1)
            if score > max_level:
                max_level = score

        # Evaluate explicit rules
        for rule in self._rules:
            if rule.matches(data_types, regulations, geography):
                matched.append(rule)
                if rule.minimum_level > max_level:
                    max_level = rule.minimum_level

        justifications = [
            f"Rule '{rule.rule_id}': {rule.description} → L{rule.minimum_level}"
            for rule in matched
        ]

        return RuleMatchResult(
            matched_rules=matched,
            rule_driven_level=SovereigntyLevel(max(1, min(7, max_level))),
            rule_justifications=justifications,
        )

    def add_rule(self, rule: ClassificationRule) -> None:
        """Add a rule at runtime.

        Parameters
        ----------
        rule:
            The ClassificationRule to append. Duplicate IDs are allowed
            (last-writer-wins if two rules have the same ID is not enforced;
            both will be evaluated).
        """
        self._rules.append(rule)

    @property
    def rules(self) -> list[ClassificationRule]:
        """Return a copy of the current rule list."""
        return list(self._rules)


__all__ = [
    "ClassificationRule",
    "ClassificationRules",
    "RuleMatchResult",
]
