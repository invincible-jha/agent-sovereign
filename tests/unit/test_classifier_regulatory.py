"""Unit tests for agent_sovereign.classifier.regulatory."""
from __future__ import annotations

import pytest

from agent_sovereign.classifier.levels import SovereigntyLevel
from agent_sovereign.classifier.regulatory import REGULATORY_MINIMUMS, RegulatoryMapper


class TestRegulatoryMinimums:
    def test_gdpr_requires_l6(self) -> None:
        assert REGULATORY_MINIMUMS["GDPR"] == 6

    def test_itar_requires_l7(self) -> None:
        assert REGULATORY_MINIMUMS["ITAR"] == 7

    def test_hipaa_requires_l3(self) -> None:
        assert REGULATORY_MINIMUMS["HIPAA"] == 3

    def test_fedramp_high_requires_l5(self) -> None:
        assert REGULATORY_MINIMUMS["FedRAMP_High"] == 5

    def test_fedramp_moderate_requires_l4(self) -> None:
        assert REGULATORY_MINIMUMS["FedRAMP_Moderate"] == 4

    def test_ccpa_requires_l2(self) -> None:
        assert REGULATORY_MINIMUMS["CCPA"] == 2

    def test_sox_requires_l3(self) -> None:
        assert REGULATORY_MINIMUMS["SOX"] == 3

    def test_pci_dss_requires_l3(self) -> None:
        assert REGULATORY_MINIMUMS["PCI_DSS"] == 3


class TestRegulatoryMapperMinimumLevelFor:
    def setup_method(self) -> None:
        self.mapper = RegulatoryMapper()

    def test_gdpr_returns_l6(self) -> None:
        level = self.mapper.minimum_level_for("GDPR")
        assert level == SovereigntyLevel.L6_CLASSIFIED

    def test_itar_returns_l7(self) -> None:
        level = self.mapper.minimum_level_for("ITAR")
        assert level == SovereigntyLevel.L7_AIRGAPPED

    def test_hipaa_returns_l3(self) -> None:
        level = self.mapper.minimum_level_for("HIPAA")
        assert level == SovereigntyLevel.L3_HYBRID

    def test_ccpa_returns_l2(self) -> None:
        level = self.mapper.minimum_level_for("CCPA")
        assert level == SovereigntyLevel.L2_CLOUD_DEDICATED

    def test_unknown_regulation_raises_key_error(self) -> None:
        with pytest.raises(KeyError, match="UNKNOWN_REG"):
            self.mapper.minimum_level_for("UNKNOWN_REG")

    def test_key_error_includes_known_regulations(self) -> None:
        with pytest.raises(KeyError) as exc_info:
            self.mapper.minimum_level_for("NOT_REAL")
        assert "Known regulations" in str(exc_info.value)


class TestRegulatoryMapperCombinedMinimum:
    def setup_method(self) -> None:
        self.mapper = RegulatoryMapper()

    def test_empty_list_returns_l1(self) -> None:
        level = self.mapper.combined_minimum([])
        assert level == SovereigntyLevel.L1_CLOUD

    def test_single_regulation_returns_its_level(self) -> None:
        level = self.mapper.combined_minimum(["HIPAA"])
        assert level == SovereigntyLevel.L3_HYBRID

    def test_stricter_regulation_wins(self) -> None:
        level = self.mapper.combined_minimum(["HIPAA", "GDPR"])
        assert level == SovereigntyLevel.L6_CLASSIFIED

    def test_itar_dominates_all(self) -> None:
        level = self.mapper.combined_minimum(["HIPAA", "GDPR", "ITAR", "CCPA"])
        assert level == SovereigntyLevel.L7_AIRGAPPED

    def test_unknown_regulations_are_skipped(self) -> None:
        level = self.mapper.combined_minimum(["HIPAA", "NOT_A_REGULATION"])
        assert level == SovereigntyLevel.L3_HYBRID

    def test_all_unknown_regulations_returns_l1(self) -> None:
        level = self.mapper.combined_minimum(["FAKE1", "FAKE2"])
        assert level == SovereigntyLevel.L1_CLOUD


class TestRegulatoryMapperDriversFor:
    def setup_method(self) -> None:
        self.mapper = RegulatoryMapper()

    def test_known_regulations_returned(self) -> None:
        drivers = self.mapper.drivers_for(["HIPAA", "SOX"])
        assert "HIPAA" in drivers
        assert "SOX" in drivers

    def test_unknown_regulations_excluded(self) -> None:
        drivers = self.mapper.drivers_for(["HIPAA", "UNKNOWN"])
        assert "UNKNOWN" not in drivers

    def test_empty_list_returns_empty_dict(self) -> None:
        assert self.mapper.drivers_for([]) == {}

    def test_values_are_sovereignty_levels(self) -> None:
        drivers = self.mapper.drivers_for(["GDPR", "ITAR"])
        for level in drivers.values():
            assert isinstance(level, SovereigntyLevel)


class TestRegulatoryMapperDescribeAndKnown:
    def setup_method(self) -> None:
        self.mapper = RegulatoryMapper()

    def test_describe_returns_string(self) -> None:
        description = self.mapper.describe("GDPR")
        assert isinstance(description, str)
        assert len(description) > 0

    def test_describe_unknown_returns_generic_message(self) -> None:
        description = self.mapper.describe("NOT_A_REGULATION")
        assert "No description available" in description

    def test_known_regulations_is_sorted(self) -> None:
        known = self.mapper.known_regulations()
        assert known == sorted(known)

    def test_known_regulations_includes_gdpr(self) -> None:
        assert "GDPR" in self.mapper.known_regulations()

    def test_known_regulations_includes_itar(self) -> None:
        assert "ITAR" in self.mapper.known_regulations()


class TestRegulatoryMapperAdditionalMinimums:
    def test_additional_minimum_overrides_builtin(self) -> None:
        mapper = RegulatoryMapper(additional_minimums={"HIPAA": 5})
        assert mapper.minimum_level_for("HIPAA") == SovereigntyLevel.L5_FULLY_LOCAL

    def test_additional_minimum_adds_new_regulation(self) -> None:
        mapper = RegulatoryMapper(additional_minimums={"MY_CUSTOM_REG": 4})
        assert mapper.minimum_level_for("MY_CUSTOM_REG") == SovereigntyLevel.L4_LOCAL_AUGMENTED

    def test_custom_regulation_appears_in_known(self) -> None:
        mapper = RegulatoryMapper(additional_minimums={"CUSTOM": 2})
        assert "CUSTOM" in mapper.known_regulations()
