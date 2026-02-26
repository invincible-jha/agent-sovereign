"""Unit tests for agent_sovereign.classifier.levels."""
from __future__ import annotations

import pytest

from agent_sovereign.classifier.levels import (
    CAPABILITY_REQUIREMENTS,
    LEVEL_DESCRIPTIONS,
    SovereigntyLevel,
    get_capability_requirements,
    get_level_description,
)


class TestSovereigntyLevelEnum:
    def test_all_seven_levels_exist(self) -> None:
        levels = list(SovereigntyLevel)
        assert len(levels) == 7

    def test_l1_is_lowest(self) -> None:
        assert SovereigntyLevel.L1_CLOUD == 1

    def test_l7_is_highest(self) -> None:
        assert SovereigntyLevel.L7_AIRGAPPED == 7

    def test_levels_are_ordered_ascending(self) -> None:
        levels = list(SovereigntyLevel)
        values = [level.value for level in levels]
        assert values == sorted(values)

    def test_l1_less_than_l7(self) -> None:
        assert SovereigntyLevel.L1_CLOUD < SovereigntyLevel.L7_AIRGAPPED

    def test_l4_between_l3_and_l5(self) -> None:
        assert SovereigntyLevel.L3_HYBRID < SovereigntyLevel.L4_LOCAL_AUGMENTED
        assert SovereigntyLevel.L4_LOCAL_AUGMENTED < SovereigntyLevel.L5_FULLY_LOCAL

    def test_all_level_names_contain_prefix(self) -> None:
        for level in SovereigntyLevel:
            assert level.name.startswith("L")

    def test_level_from_integer(self) -> None:
        assert SovereigntyLevel(3) == SovereigntyLevel.L3_HYBRID

    def test_level_from_integer_all_values(self) -> None:
        for expected_value in range(1, 8):
            level = SovereigntyLevel(expected_value)
            assert level.value == expected_value

    def test_integer_comparison(self) -> None:
        assert SovereigntyLevel.L5_FULLY_LOCAL >= 5
        assert SovereigntyLevel.L2_CLOUD_DEDICATED < 3

    def test_l6_classified_name(self) -> None:
        assert SovereigntyLevel.L6_CLASSIFIED.name == "L6_CLASSIFIED"

    def test_l7_airgapped_name(self) -> None:
        assert SovereigntyLevel.L7_AIRGAPPED.name == "L7_AIRGAPPED"

    def test_max_of_levels(self) -> None:
        result = max(SovereigntyLevel.L2_CLOUD_DEDICATED, SovereigntyLevel.L5_FULLY_LOCAL)
        assert result == SovereigntyLevel.L5_FULLY_LOCAL

    def test_min_of_levels(self) -> None:
        result = min(SovereigntyLevel.L6_CLASSIFIED, SovereigntyLevel.L1_CLOUD)
        assert result == SovereigntyLevel.L1_CLOUD


class TestLevelDescriptions:
    def test_every_level_has_a_description(self) -> None:
        for level in SovereigntyLevel:
            assert level in LEVEL_DESCRIPTIONS

    def test_descriptions_are_non_empty_strings(self) -> None:
        for level, description in LEVEL_DESCRIPTIONS.items():
            assert isinstance(description, str)
            assert len(description) > 0

    def test_get_level_description_returns_string(self) -> None:
        description = get_level_description(SovereigntyLevel.L1_CLOUD)
        assert isinstance(description, str)

    def test_l1_description_mentions_cloud(self) -> None:
        description = get_level_description(SovereigntyLevel.L1_CLOUD)
        assert "cloud" in description.lower()

    def test_l7_description_mentions_air_gap(self) -> None:
        description = get_level_description(SovereigntyLevel.L7_AIRGAPPED)
        assert "air" in description.lower()

    def test_descriptions_differ_per_level(self) -> None:
        descriptions = [get_level_description(level) for level in SovereigntyLevel]
        assert len(set(descriptions)) == 7


class TestCapabilityRequirements:
    def test_every_level_has_capability_requirements(self) -> None:
        for level in SovereigntyLevel:
            assert level in CAPABILITY_REQUIREMENTS

    def test_each_requirement_has_eight_keys(self) -> None:
        expected_keys = {
            "network_access",
            "data_storage",
            "encryption_at_rest",
            "encryption_in_transit",
            "model_hosting",
            "audit_logging",
            "key_management",
            "update_mechanism",
        }
        for level in SovereigntyLevel:
            reqs = CAPABILITY_REQUIREMENTS[level]
            assert set(reqs.keys()) == expected_keys

    def test_get_capability_requirements_returns_dict(self) -> None:
        reqs = get_capability_requirements(SovereigntyLevel.L3_HYBRID)
        assert isinstance(reqs, dict)

    def test_get_capability_requirements_returns_copy(self) -> None:
        reqs_a = get_capability_requirements(SovereigntyLevel.L1_CLOUD)
        reqs_b = get_capability_requirements(SovereigntyLevel.L1_CLOUD)
        reqs_a["network_access"] = "mutated"
        assert reqs_b["network_access"] != "mutated"

    def test_l7_network_access_is_none(self) -> None:
        reqs = get_capability_requirements(SovereigntyLevel.L7_AIRGAPPED)
        assert reqs["network_access"] == "none"

    def test_l1_network_access_is_unrestricted(self) -> None:
        reqs = get_capability_requirements(SovereigntyLevel.L1_CLOUD)
        assert reqs["network_access"] == "unrestricted"

    def test_l4_encryption_is_fips(self) -> None:
        reqs = get_capability_requirements(SovereigntyLevel.L4_LOCAL_AUGMENTED)
        assert "fips" in reqs["encryption_at_rest"].lower()
