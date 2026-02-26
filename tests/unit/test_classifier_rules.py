"""Unit tests for agent_sovereign.classifier.rules."""
from __future__ import annotations

import pytest

from agent_sovereign.classifier.levels import SovereigntyLevel
from agent_sovereign.classifier.rules import (
    ClassificationRule,
    ClassificationRules,
    RuleMatchResult,
)


class TestClassificationRuleMatches:
    def _make_rule(
        self,
        data_types: list[str] | None = None,
        regulations: list[str] | None = None,
        geographies: list[str] | None = None,
        minimum_level: int = 3,
    ) -> ClassificationRule:
        return ClassificationRule(
            rule_id="test_rule",
            description="A test rule",
            minimum_level=minimum_level,
            data_types=data_types or [],
            regulations=regulations or [],
            geographies=geographies or [],
        )

    def test_empty_rule_matches_everything(self) -> None:
        rule = self._make_rule()
        assert rule.matches(["phi"], ["HIPAA"], "EU") is True

    def test_empty_rule_matches_empty_inputs(self) -> None:
        rule = self._make_rule()
        assert rule.matches([], [], None) is True

    def test_data_type_match_succeeds(self) -> None:
        rule = self._make_rule(data_types=["phi"])
        assert rule.matches(["phi", "medical_records"], [], None) is True

    def test_data_type_match_fails_when_not_present(self) -> None:
        rule = self._make_rule(data_types=["classified"])
        assert rule.matches(["phi"], [], None) is False

    def test_regulation_match_succeeds(self) -> None:
        rule = self._make_rule(regulations=["HIPAA"])
        assert rule.matches([], ["HIPAA", "GDPR"], None) is True

    def test_regulation_match_fails(self) -> None:
        rule = self._make_rule(regulations=["ITAR"])
        assert rule.matches([], ["HIPAA"], None) is False

    def test_geography_match_succeeds(self) -> None:
        rule = self._make_rule(geographies=["EU", "EEA"])
        assert rule.matches([], [], "EU") is True

    def test_geography_match_fails(self) -> None:
        rule = self._make_rule(geographies=["EU"])
        assert rule.matches([], [], "US") is False

    def test_geography_none_fails_when_required(self) -> None:
        rule = self._make_rule(geographies=["EU"])
        assert rule.matches([], [], None) is False

    def test_all_conditions_must_be_met(self) -> None:
        rule = self._make_rule(
            data_types=["phi"],
            regulations=["HIPAA"],
            geographies=["US"],
        )
        # All three match
        assert rule.matches(["phi"], ["HIPAA"], "US") is True
        # Missing geography
        assert rule.matches(["phi"], ["HIPAA"], "EU") is False
        # Missing regulation
        assert rule.matches(["phi"], [], "US") is False
        # Missing data type
        assert rule.matches([], ["HIPAA"], "US") is False


class TestClassificationRulesDefaultRules:
    def setup_method(self) -> None:
        self.engine = ClassificationRules()

    def test_default_rules_loads_without_error(self) -> None:
        assert len(self.engine.rules) > 0

    def test_rules_property_returns_copy(self) -> None:
        rules_a = self.engine.rules
        rules_b = self.engine.rules
        assert rules_a is not rules_b

    def test_phi_data_type_raises_level(self) -> None:
        result = self.engine.evaluate(data_types=["phi"], regulations=[], geography=None)
        assert result.rule_driven_level >= SovereigntyLevel.L5_FULLY_LOCAL

    def test_classified_data_requires_l7(self) -> None:
        result = self.engine.evaluate(data_types=["classified"], regulations=[], geography=None)
        assert result.rule_driven_level == SovereigntyLevel.L7_AIRGAPPED

    def test_itar_data_requires_l7(self) -> None:
        result = self.engine.evaluate(
            data_types=["itar_technical_data"], regulations=[], geography=None
        )
        assert result.rule_driven_level == SovereigntyLevel.L7_AIRGAPPED

    def test_biometric_data_requires_at_least_l5(self) -> None:
        result = self.engine.evaluate(
            data_types=["biometric_data"], regulations=[], geography=None
        )
        assert result.rule_driven_level >= SovereigntyLevel.L5_FULLY_LOCAL

    def test_genetic_data_requires_at_least_l5(self) -> None:
        result = self.engine.evaluate(
            data_types=["genetic_data"], regulations=[], geography=None
        )
        assert result.rule_driven_level >= SovereigntyLevel.L5_FULLY_LOCAL

    def test_hipaa_with_phi_fires_combination_rule(self) -> None:
        result = self.engine.evaluate(
            data_types=["phi", "medical_records"],
            regulations=["HIPAA"],
            geography=None,
        )
        assert result.rule_driven_level >= SovereigntyLevel.L4_LOCAL_AUGMENTED
        assert any("hipaa_phi_combination" == r.rule_id for r in result.matched_rules)

    def test_gdpr_in_eu_fires_combination_rule(self) -> None:
        result = self.engine.evaluate(
            data_types=[],
            regulations=["GDPR"],
            geography="EU",
        )
        assert result.rule_driven_level >= SovereigntyLevel.L6_CLASSIFIED

    def test_no_match_returns_l1(self) -> None:
        result = self.engine.evaluate(data_types=[], regulations=[], geography=None)
        assert result.rule_driven_level == SovereigntyLevel.L1_CLOUD

    def test_justifications_populated_for_matched_rules(self) -> None:
        result = self.engine.evaluate(data_types=["phi"], regulations=[], geography=None)
        assert len(result.rule_justifications) > 0

    def test_matched_rules_contains_correct_rule_ids(self) -> None:
        result = self.engine.evaluate(
            data_types=["classified"], regulations=[], geography=None
        )
        matched_ids = [r.rule_id for r in result.matched_rules]
        assert "classified_airgap" in matched_ids


class TestClassificationRulesFromYamlString:
    _CUSTOM_YAML = """\
version: "1.0"
rules:
  - id: custom_rule_1
    description: "Custom rule for testing"
    data_types: ["test_data"]
    minimum_level: 4
"""

    def test_load_from_yaml_string_succeeds(self) -> None:
        engine = ClassificationRules(yaml_source=self._CUSTOM_YAML)
        assert len(engine.rules) == 1
        assert engine.rules[0].rule_id == "custom_rule_1"

    def test_custom_rule_fires(self) -> None:
        engine = ClassificationRules(yaml_source=self._CUSTOM_YAML)
        result = engine.evaluate(data_types=["test_data"], regulations=[], geography=None)
        assert result.rule_driven_level >= SovereigntyLevel.L4_LOCAL_AUGMENTED

    def test_invalid_yaml_missing_rules_key_raises(self) -> None:
        bad_yaml = "version: '1.0'\nno_rules: []"
        with pytest.raises(ValueError, match="'rules' key"):
            ClassificationRules(yaml_source=bad_yaml)


class TestClassificationRulesFromFile:
    def test_load_from_path_object(self, tmp_path: pytest.TempPathFactory) -> None:
        import pathlib

        yaml_content = """\
version: "1.0"
rules:
  - id: file_rule
    description: "Loaded from file"
    data_types: ["phi"]
    minimum_level: 5
"""
        rules_file = pathlib.Path(str(tmp_path)) / "rules.yaml"
        rules_file.write_text(yaml_content, encoding="utf-8")
        engine = ClassificationRules(yaml_source=rules_file)
        assert any(r.rule_id == "file_rule" for r in engine.rules)


class TestClassificationRulesAddRule:
    def test_add_rule_appends_to_list(self) -> None:
        engine = ClassificationRules()
        initial_count = len(engine.rules)
        new_rule = ClassificationRule(
            rule_id="dynamic_rule",
            description="Added at runtime",
            minimum_level=3,
            data_types=["employee_data"],
        )
        engine.add_rule(new_rule)
        assert len(engine.rules) == initial_count + 1

    def test_added_rule_fires_on_evaluate(self) -> None:
        engine = ClassificationRules()
        new_rule = ClassificationRule(
            rule_id="runtime_rule",
            description="Runtime override",
            minimum_level=7,
            regulations=["FAKE_REG"],
        )
        engine.add_rule(new_rule)
        result = engine.evaluate(data_types=[], regulations=["FAKE_REG"], geography=None)
        assert result.rule_driven_level == SovereigntyLevel.L7_AIRGAPPED
