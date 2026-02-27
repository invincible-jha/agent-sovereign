"""Tests for agent_sovereign.classification.levels."""
from __future__ import annotations

import pytest

from agent_sovereign.classification.levels import (
    AgentConfig,
    DeploymentLevel,
    LEVEL_DESCRIPTIONS,
    LEVEL_REQUIREMENTS,
    SovereigntyClassifier,
    SovereigntyLevelResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def classifier() -> SovereigntyClassifier:
    return SovereigntyClassifier()


# ---------------------------------------------------------------------------
# DeploymentLevel enum tests
# ---------------------------------------------------------------------------


class TestDeploymentLevel:
    def test_all_five_levels_exist(self) -> None:
        levels = list(DeploymentLevel)
        assert len(levels) == 5

    def test_level_values(self) -> None:
        assert DeploymentLevel.L1_CLOUD.value == "L1_CLOUD"
        assert DeploymentLevel.L2_HYBRID.value == "L2_HYBRID"
        assert DeploymentLevel.L3_ON_PREM.value == "L3_ON_PREM"
        assert DeploymentLevel.L4_AIR_GAPPED.value == "L4_AIR_GAPPED"
        assert DeploymentLevel.L5_EMBEDDED.value == "L5_EMBEDDED"

    def test_level_descriptions_covers_all(self) -> None:
        for level in DeploymentLevel:
            assert level in LEVEL_DESCRIPTIONS
            assert len(LEVEL_DESCRIPTIONS[level]) > 10

    def test_level_requirements_covers_all(self) -> None:
        for level in DeploymentLevel:
            assert level in LEVEL_REQUIREMENTS
            assert isinstance(LEVEL_REQUIREMENTS[level], list)


# ---------------------------------------------------------------------------
# L1_CLOUD classification
# ---------------------------------------------------------------------------


class TestL1CloudClassification:
    def test_default_config_is_cloud(self, classifier: SovereigntyClassifier) -> None:
        config = AgentConfig()
        result = classifier.classify(config)
        assert result.level == DeploymentLevel.L1_CLOUD

    def test_pure_cloud_config(self, classifier: SovereigntyClassifier) -> None:
        config = AgentConfig(
            uses_cloud_inference=True,
            uses_local_inference=False,
            data_leaves_boundary=True,
            has_cloud_storage=True,
        )
        result = classifier.classify(config)
        assert result.level == DeploymentLevel.L1_CLOUD
        assert result.confidence == 1.0

    def test_cloud_result_has_description(self, classifier: SovereigntyClassifier) -> None:
        result = classifier.classify(AgentConfig())
        assert "cloud" in result.description.lower()

    def test_cloud_result_has_requirements(self, classifier: SovereigntyClassifier) -> None:
        result = classifier.classify(AgentConfig())
        assert "cloud_provider" in result.requirements

    def test_cloud_result_has_signals(self, classifier: SovereigntyClassifier) -> None:
        result = classifier.classify(AgentConfig())
        assert len(result.config_signals) > 0


# ---------------------------------------------------------------------------
# L2_HYBRID classification
# ---------------------------------------------------------------------------


class TestL2HybridClassification:
    def test_hybrid_both_inference(self, classifier: SovereigntyClassifier) -> None:
        config = AgentConfig(
            uses_cloud_inference=True,
            uses_local_inference=True,
        )
        result = classifier.classify(config)
        assert result.level == DeploymentLevel.L2_HYBRID

    def test_hybrid_confidence_reduced_when_data_stays(
        self, classifier: SovereigntyClassifier
    ) -> None:
        config = AgentConfig(
            uses_cloud_inference=True,
            uses_local_inference=True,
            data_leaves_boundary=False,
        )
        result = classifier.classify(config)
        assert result.level == DeploymentLevel.L2_HYBRID
        assert result.confidence < 1.0

    def test_hybrid_description(self, classifier: SovereigntyClassifier) -> None:
        config = AgentConfig(uses_cloud_inference=True, uses_local_inference=True)
        result = classifier.classify(config)
        assert len(result.description) > 10

    def test_hybrid_requirements(self, classifier: SovereigntyClassifier) -> None:
        config = AgentConfig(uses_cloud_inference=True, uses_local_inference=True)
        result = classifier.classify(config)
        assert "local_inference" in result.requirements


# ---------------------------------------------------------------------------
# L3_ON_PREM classification
# ---------------------------------------------------------------------------


class TestL3OnPremClassification:
    def test_on_prem_self_hosted_no_cloud(self, classifier: SovereigntyClassifier) -> None:
        config = AgentConfig(
            uses_cloud_inference=False,
            uses_local_inference=True,
            self_hosted=True,
            data_leaves_boundary=False,
            has_cloud_storage=False,
        )
        result = classifier.classify(config)
        assert result.level == DeploymentLevel.L3_ON_PREM

    def test_on_prem_confidence_reduced_with_cloud_storage(
        self, classifier: SovereigntyClassifier
    ) -> None:
        config = AgentConfig(
            uses_cloud_inference=False,
            self_hosted=True,
            data_leaves_boundary=False,
            has_cloud_storage=True,  # conflict
        )
        result = classifier.classify(config)
        assert result.level == DeploymentLevel.L3_ON_PREM
        assert result.confidence < 1.0

    def test_on_prem_requirements(self, classifier: SovereigntyClassifier) -> None:
        config = AgentConfig(
            uses_cloud_inference=False,
            self_hosted=True,
            data_leaves_boundary=False,
        )
        result = classifier.classify(config)
        assert "self_hosted_infra" in result.requirements

    def test_on_prem_local_inference_path(self, classifier: SovereigntyClassifier) -> None:
        config = AgentConfig(
            uses_cloud_inference=False,
            uses_local_inference=True,
            self_hosted=True,
        )
        result = classifier.classify(config)
        assert result.level == DeploymentLevel.L3_ON_PREM


# ---------------------------------------------------------------------------
# L4_AIR_GAPPED classification
# ---------------------------------------------------------------------------


class TestL4AirGappedClassification:
    def test_air_gapped_config(self, classifier: SovereigntyClassifier) -> None:
        config = AgentConfig(
            air_gapped=True,
            self_hosted=True,
            requires_network=False,
            uses_cloud_inference=False,
            data_leaves_boundary=False,
        )
        result = classifier.classify(config)
        assert result.level == DeploymentLevel.L4_AIR_GAPPED

    def test_air_gapped_confidence_reduced_with_network(
        self, classifier: SovereigntyClassifier
    ) -> None:
        config = AgentConfig(
            air_gapped=True,
            requires_network=True,  # conflict
        )
        result = classifier.classify(config)
        assert result.level == DeploymentLevel.L4_AIR_GAPPED
        assert result.confidence < 1.0

    def test_air_gapped_requirements(self, classifier: SovereigntyClassifier) -> None:
        config = AgentConfig(air_gapped=True, requires_network=False)
        result = classifier.classify(config)
        assert "no_network" in result.requirements

    def test_air_gapped_description(self, classifier: SovereigntyClassifier) -> None:
        config = AgentConfig(air_gapped=True)
        result = classifier.classify(config)
        assert len(result.description) > 10


# ---------------------------------------------------------------------------
# L5_EMBEDDED classification
# ---------------------------------------------------------------------------


class TestL5EmbeddedClassification:
    def test_embedded_device_config(self, classifier: SovereigntyClassifier) -> None:
        config = AgentConfig(
            embedded_device=True,
            requires_network=False,
            uses_cloud_inference=False,
        )
        result = classifier.classify(config)
        assert result.level == DeploymentLevel.L5_EMBEDDED

    def test_embedded_confidence_reduced_when_needs_network(
        self, classifier: SovereigntyClassifier
    ) -> None:
        config = AgentConfig(
            embedded_device=True,
            requires_network=True,  # unusual for embedded
        )
        result = classifier.classify(config)
        assert result.level == DeploymentLevel.L5_EMBEDDED
        assert result.confidence < 1.0

    def test_embedded_requirements(self, classifier: SovereigntyClassifier) -> None:
        config = AgentConfig(embedded_device=True, requires_network=False)
        result = classifier.classify(config)
        assert "embedded_runtime" in result.requirements

    def test_embedded_takes_priority_over_air_gapped(
        self, classifier: SovereigntyClassifier
    ) -> None:
        config = AgentConfig(
            embedded_device=True,
            air_gapped=True,
            requires_network=False,
        )
        result = classifier.classify(config)
        assert result.level == DeploymentLevel.L5_EMBEDDED


# ---------------------------------------------------------------------------
# SovereigntyLevelResult frozen dataclass
# ---------------------------------------------------------------------------


class TestSovereigntyLevelResult:
    def test_result_is_frozen(self, classifier: SovereigntyClassifier) -> None:
        result = classifier.classify(AgentConfig())
        with pytest.raises((AttributeError, TypeError)):
            result.level = DeploymentLevel.L5_EMBEDDED  # type: ignore[misc]

    def test_confidence_clamped_to_valid_range(
        self, classifier: SovereigntyClassifier
    ) -> None:
        # Pile on conflicts to try to drive confidence below 0
        config = AgentConfig(
            air_gapped=True,
            requires_network=True,
            self_hosted=False,
        )
        result = classifier.classify(config)
        assert 0.0 <= result.confidence <= 1.0

    def test_result_has_rationale(self, classifier: SovereigntyClassifier) -> None:
        for level_config in [
            AgentConfig(),
            AgentConfig(uses_cloud_inference=True, uses_local_inference=True),
            AgentConfig(air_gapped=True),
            AgentConfig(embedded_device=True),
        ]:
            result = classifier.classify(level_config)
            assert len(result.rationale) > 0


# ---------------------------------------------------------------------------
# Helper methods on classifier
# ---------------------------------------------------------------------------


class TestClassifierHelpers:
    def test_get_level_description(self, classifier: SovereigntyClassifier) -> None:
        for level in DeploymentLevel:
            desc = classifier.get_level_description(level)
            assert isinstance(desc, str)
            assert len(desc) > 10

    def test_get_level_requirements(self, classifier: SovereigntyClassifier) -> None:
        for level in DeploymentLevel:
            reqs = classifier.get_level_requirements(level)
            assert isinstance(reqs, list)
