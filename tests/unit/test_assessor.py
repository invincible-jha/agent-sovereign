"""Tests for SovereigntyAssessor and SovereigntyAssessment."""
from __future__ import annotations

import pytest

from agent_sovereign.classifier.assessor import (
    SovereigntyAssessment,
    SovereigntyAssessor,
    _DEPLOYMENT_TEMPLATE_NAMES,
    _GEOGRAPHY_MINIMUMS,
)
from agent_sovereign.classifier.levels import SovereigntyLevel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def assessor() -> SovereigntyAssessor:
    return SovereigntyAssessor()


# ---------------------------------------------------------------------------
# SovereigntyAssessment dataclass
# ---------------------------------------------------------------------------

class TestSovereigntyAssessment:
    def test_fields_accessible(self) -> None:
        assessment = SovereigntyAssessment(
            level=SovereigntyLevel.L3_HYBRID,
            score=3,
            justification="test",
            data_sensitivity=2,
            regulatory_drivers={"HIPAA": SovereigntyLevel.L3_HYBRID},
            deployment_template="l3_hybrid",
        )
        assert assessment.score == 3
        assert assessment.level == SovereigntyLevel.L3_HYBRID
        assert assessment.deployment_template == "l3_hybrid"
        assert assessment.warnings == []
        assert assessment.capability_requirements == {}

    def test_default_warnings_empty(self) -> None:
        assessment = SovereigntyAssessment(
            level=SovereigntyLevel.L1_CLOUD,
            score=1,
            justification="baseline",
            data_sensitivity=1,
            regulatory_drivers={},
            deployment_template="l1_cloud",
        )
        assert assessment.warnings == []

    def test_warnings_can_be_set(self) -> None:
        warnings_list = ["warning one"]
        assessment = SovereigntyAssessment(
            level=SovereigntyLevel.L2_CLOUD_DEDICATED,
            score=2,
            justification="test",
            data_sensitivity=1,
            regulatory_drivers={},
            deployment_template="l2_cloud_fallback",
            warnings=warnings_list,
        )
        assert len(assessment.warnings) == 1
        assert assessment.warnings[0] == "warning one"


# ---------------------------------------------------------------------------
# Geography minimums constant
# ---------------------------------------------------------------------------

class TestGeographyMinimums:
    def test_eu_is_level_6(self) -> None:
        assert _GEOGRAPHY_MINIMUMS["EU"] == 6

    def test_us_is_level_2(self) -> None:
        assert _GEOGRAPHY_MINIMUMS["US"] == 2

    def test_global_is_level_1(self) -> None:
        assert _GEOGRAPHY_MINIMUMS["GLOBAL"] == 1

    def test_us_dod_is_level_5(self) -> None:
        assert _GEOGRAPHY_MINIMUMS["US_DOD"] == 5


# ---------------------------------------------------------------------------
# Deployment template names
# ---------------------------------------------------------------------------

class TestDeploymentTemplateNames:
    def test_all_levels_covered(self) -> None:
        for level_value in range(1, 8):
            assert level_value in _DEPLOYMENT_TEMPLATE_NAMES

    def test_level_7_is_airgapped(self) -> None:
        assert _DEPLOYMENT_TEMPLATE_NAMES[7] == "l7_airgapped"

    def test_level_1_is_cloud(self) -> None:
        assert _DEPLOYMENT_TEMPLATE_NAMES[1] == "l1_cloud"


# ---------------------------------------------------------------------------
# SovereigntyAssessor construction
# ---------------------------------------------------------------------------

class TestAssessorConstruction:
    def test_default_org_minimum_is_l1(self) -> None:
        assessor = SovereigntyAssessor()
        assert assessor._org_minimum == SovereigntyLevel.L1_CLOUD

    def test_custom_org_minimum(self) -> None:
        assessor = SovereigntyAssessor(org_minimum=SovereigntyLevel.L3_HYBRID)
        assert assessor._org_minimum == SovereigntyLevel.L3_HYBRID

    def test_additional_geo_minimums_merged(self) -> None:
        assessor = SovereigntyAssessor(additional_geo_minimums={"XX": 5})
        assert assessor._geo_minimums["XX"] == 5
        assert "EU" in assessor._geo_minimums  # built-ins preserved

    def test_additional_geo_minimums_override(self) -> None:
        assessor = SovereigntyAssessor(additional_geo_minimums={"EU": 7})
        assert assessor._geo_minimums["EU"] == 7


# ---------------------------------------------------------------------------
# SovereigntyAssessor.assess — baseline
# ---------------------------------------------------------------------------

class TestAssessorAssess:
    def test_baseline_no_inputs_returns_l1(self, assessor: SovereigntyAssessor) -> None:
        result = assessor.assess(data_types=[], regulations=[])
        assert result.score == 1
        assert result.level == SovereigntyLevel.L1_CLOUD
        assert result.deployment_template == "l1_cloud"

    def test_phi_data_drives_level_up(self, assessor: SovereigntyAssessor) -> None:
        result = assessor.assess(data_types=["phi"], regulations=[])
        assert result.score >= 3

    def test_hipaa_regulation_drives_level(self, assessor: SovereigntyAssessor) -> None:
        result = assessor.assess(data_types=[], regulations=["HIPAA"])
        assert result.score >= 3

    def test_eu_geography_drives_level_6(self, assessor: SovereigntyAssessor) -> None:
        result = assessor.assess(data_types=[], regulations=[], geography="EU")
        assert result.score >= 6

    def test_unknown_geography_produces_warning(self, assessor: SovereigntyAssessor) -> None:
        result = assessor.assess(data_types=[], regulations=[], geography="ZZZZ")
        assert any("ZZZZ" in w for w in result.warnings)

    def test_unknown_regulation_produces_warning(self, assessor: SovereigntyAssessor) -> None:
        result = assessor.assess(data_types=[], regulations=["UNKNOWN_REG"])
        assert any("UNKNOWN_REG" in w for w in result.warnings)

    def test_org_minimum_overrides_per_call(self, assessor: SovereigntyAssessor) -> None:
        result = assessor.assess(
            data_types=[],
            regulations=[],
            org_minimum=SovereigntyLevel.L4_LOCAL_AUGMENTED,
        )
        assert result.score >= 4

    def test_instance_org_minimum_respected(self) -> None:
        assessor = SovereigntyAssessor(org_minimum=SovereigntyLevel.L5_FULLY_LOCAL)
        result = assessor.assess(data_types=[], regulations=[])
        assert result.score >= 5

    def test_gdpr_at_l6_adds_warning(self, assessor: SovereigntyAssessor) -> None:
        result = assessor.assess(data_types=[], regulations=["GDPR"], geography="EU")
        assert any("GDPR" in w for w in result.warnings)

    def test_l7_adds_airgap_warning(self) -> None:
        assessor = SovereigntyAssessor(org_minimum=SovereigntyLevel.L7_AIRGAPPED)
        result = assessor.assess(data_types=[], regulations=[])
        assert any("air-gap" in w.lower() or "L7" in w for w in result.warnings)

    def test_assessment_has_justification(self, assessor: SovereigntyAssessor) -> None:
        result = assessor.assess(data_types=["phi"], regulations=["HIPAA"])
        assert len(result.justification) > 0

    def test_assessment_data_sensitivity_field(self, assessor: SovereigntyAssessor) -> None:
        result = assessor.assess(data_types=["phi"], regulations=[])
        assert result.data_sensitivity >= 1

    def test_assessment_regulatory_drivers_populated(self, assessor: SovereigntyAssessor) -> None:
        result = assessor.assess(data_types=[], regulations=["HIPAA"])
        assert "HIPAA" in result.regulatory_drivers

    def test_assessment_capability_requirements_present(self, assessor: SovereigntyAssessor) -> None:
        result = assessor.assess(data_types=["phi"], regulations=["HIPAA"])
        assert isinstance(result.capability_requirements, dict)

    def test_max_driver_wins(self, assessor: SovereigntyAssessor) -> None:
        result_geo = assessor.assess(data_types=[], regulations=[], geography="EU")
        result_both = assessor.assess(data_types=["pii"], regulations=["GDPR"], geography="EU")
        # EU geography drives to 6; adding pii + GDPR shouldn't lower it
        assert result_both.score >= result_geo.score

    def test_score_clamped_to_1_7(self, assessor: SovereigntyAssessor) -> None:
        result = assessor.assess(data_types=[], regulations=[])
        assert 1 <= result.score <= 7

    def test_no_justification_parts_produces_baseline_text(
        self, assessor: SovereigntyAssessor
    ) -> None:
        result = assessor.assess(data_types=[], regulations=[])
        assert "baseline" in result.justification.lower() or "No sensitive" in result.justification

    def test_justification_with_drivers_mentions_driver(
        self, assessor: SovereigntyAssessor
    ) -> None:
        result = assessor.assess(data_types=["phi"], regulations=[])
        assert "data_sensitivity" in result.justification or "Data sensitivity" in result.justification

    def test_us_geography(self, assessor: SovereigntyAssessor) -> None:
        result = assessor.assess(data_types=[], regulations=[], geography="US")
        assert result.score >= 2

    def test_deployment_template_matches_score(self, assessor: SovereigntyAssessor) -> None:
        result = assessor.assess(data_types=["phi"], regulations=["HIPAA"])
        expected_template = _DEPLOYMENT_TEMPLATE_NAMES.get(result.score, "l1_cloud")
        assert result.deployment_template == expected_template


# ---------------------------------------------------------------------------
# SovereigntyAssessor.describe_level
# ---------------------------------------------------------------------------

class TestDescribeLevel:
    def test_returns_string(self, assessor: SovereigntyAssessor) -> None:
        description = assessor.describe_level(SovereigntyLevel.L3_HYBRID)
        assert isinstance(description, str)
        assert len(description) > 0

    def test_all_levels_have_description(self, assessor: SovereigntyAssessor) -> None:
        for level in SovereigntyLevel:
            desc = assessor.describe_level(level)
            assert isinstance(desc, str)
