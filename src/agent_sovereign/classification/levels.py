"""Sovereignty level classification for deployed agents.

Defines five deployment sovereignty levels — from fully cloud-hosted through to
device-embedded — and a :class:`SovereigntyClassifier` that maps an agent
configuration to the appropriate level.

Levels
------
L1_CLOUD     : Fully cloud-hosted; all inference and data leave the boundary.
L2_HYBRID    : Cloud + local combination; some data processed on-prem.
L3_ON_PREM   : Self-hosted infrastructure; no third-party cloud services.
L4_AIR_GAPPED: No network connectivity; fully isolated deployment.
L5_EMBEDDED  : Single-device embedded; runs on constrained hardware.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Deployment level enum
# ---------------------------------------------------------------------------


class DeploymentLevel(str, Enum):
    """The five sovereignty levels for agent deployments.

    Each level encodes the degree to which the deployment boundary is
    controlled by the organisation running the agent.
    """

    L1_CLOUD = "L1_CLOUD"
    L2_HYBRID = "L2_HYBRID"
    L3_ON_PREM = "L3_ON_PREM"
    L4_AIR_GAPPED = "L4_AIR_GAPPED"
    L5_EMBEDDED = "L5_EMBEDDED"


# ---------------------------------------------------------------------------
# Human-readable descriptions and requirements
# ---------------------------------------------------------------------------

LEVEL_DESCRIPTIONS: dict[DeploymentLevel, str] = {
    DeploymentLevel.L1_CLOUD: (
        "Fully cloud-hosted. Inference, storage, and orchestration run on "
        "third-party cloud infrastructure. Data crosses organisational boundary."
    ),
    DeploymentLevel.L2_HYBRID: (
        "Hybrid cloud + on-premises. Sensitive processing occurs locally; "
        "non-sensitive workloads may use cloud services."
    ),
    DeploymentLevel.L3_ON_PREM: (
        "Self-hosted on-premises. All inference and data remain within the "
        "organisation's own data centre. No third-party cloud services."
    ),
    DeploymentLevel.L4_AIR_GAPPED: (
        "Air-gapped — no network connectivity. The deployment runs in a "
        "physically isolated environment with no internet or WAN access."
    ),
    DeploymentLevel.L5_EMBEDDED: (
        "Device-embedded. The agent runs entirely on a single constrained "
        "hardware device (IoT, edge sensor, mobile) with local-only inference."
    ),
}

LEVEL_REQUIREMENTS: dict[DeploymentLevel, list[str]] = {
    DeploymentLevel.L1_CLOUD: ["cloud_provider"],
    DeploymentLevel.L2_HYBRID: ["cloud_provider", "local_inference"],
    DeploymentLevel.L3_ON_PREM: ["self_hosted_infra"],
    DeploymentLevel.L4_AIR_GAPPED: ["self_hosted_infra", "no_network"],
    DeploymentLevel.L5_EMBEDDED: ["embedded_runtime", "no_network"],
}


# ---------------------------------------------------------------------------
# Agent configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class AgentConfig:
    """Descriptor for an agent's deployment configuration.

    Attributes
    ----------
    uses_cloud_inference:
        Whether inference is performed on a third-party cloud API.
    uses_local_inference:
        Whether inference can also run locally (on-prem or device).
    requires_network:
        Whether the agent requires network access to function.
    self_hosted:
        Whether the agent runs on infrastructure owned by the operator.
    air_gapped:
        Whether the deployment environment has no network connectivity.
    embedded_device:
        Whether the agent is deployed on a constrained single device.
    data_leaves_boundary:
        Whether any user data is sent outside the organisational boundary.
    has_cloud_storage:
        Whether cloud object/database storage is in use.
    has_local_storage:
        Whether on-premises or device-local storage is in use.
    extra:
        Arbitrary additional metadata for custom classification rules.
    """

    uses_cloud_inference: bool = True
    uses_local_inference: bool = False
    requires_network: bool = True
    self_hosted: bool = False
    air_gapped: bool = False
    embedded_device: bool = False
    data_leaves_boundary: bool = True
    has_cloud_storage: bool = True
    has_local_storage: bool = False
    extra: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Classification result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SovereigntyLevelResult:
    """Result of classifying an agent configuration.

    Attributes
    ----------
    level:
        The assigned :class:`DeploymentLevel`.
    description:
        Human-readable description of the level.
    requirements:
        List of capability requirements for this level.
    confidence:
        A score in [0.0, 1.0] representing how confidently the config
        maps to the assigned level (1.0 = unambiguous).
    rationale:
        Explanation of why this level was assigned.
    config_signals:
        Key config flags that influenced the decision.
    """

    level: DeploymentLevel
    description: str
    requirements: list[str]
    confidence: float
    rationale: str
    config_signals: list[str]


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class SovereigntyClassifier:
    """Assess an :class:`AgentConfig` and assign a :class:`DeploymentLevel`.

    The classifier applies a priority-ordered rule chain.  The first rule
    whose conditions are satisfied determines the level.  Confidence is
    lowered when the configuration contains mixed signals.

    Example
    -------
    ::

        config = AgentConfig(air_gapped=True, self_hosted=True, requires_network=False)
        classifier = SovereigntyClassifier()
        result = classifier.classify(config)
        assert result.level == DeploymentLevel.L4_AIR_GAPPED
    """

    def classify(self, config: AgentConfig) -> SovereigntyLevelResult:
        """Classify *config* into a :class:`DeploymentLevel`.

        Parameters
        ----------
        config:
            The agent deployment configuration to analyse.

        Returns
        -------
        SovereigntyLevelResult
            The assigned level and supporting metadata.
        """
        signals: list[str] = []
        confidence = 1.0

        # L5_EMBEDDED — device-embedded, no network
        if config.embedded_device:
            signals.append("embedded_device=True")
            if not config.requires_network:
                signals.append("requires_network=False")
            else:
                confidence -= 0.2  # Network-requiring embedded is mixed
            level = DeploymentLevel.L5_EMBEDDED
            rationale = (
                "Agent is deployed on a constrained single device. "
                "Full inference must run on-device."
            )
            return self._build_result(level, confidence, rationale, signals)

        # L4_AIR_GAPPED — physically isolated, no network
        if config.air_gapped:
            signals.append("air_gapped=True")
            if config.requires_network:
                signals.append("requires_network=True (conflict)")
                confidence -= 0.3
            if not config.self_hosted:
                signals.append("self_hosted=False (conflict)")
                confidence -= 0.1
            level = DeploymentLevel.L4_AIR_GAPPED
            rationale = (
                "Deployment environment has no network connectivity. "
                "All resources must be available locally."
            )
            return self._build_result(level, confidence, rationale, signals)

        # L3_ON_PREM — self-hosted, no cloud, no data leaving boundary
        if (
            config.self_hosted
            and not config.uses_cloud_inference
            and not config.data_leaves_boundary
        ):
            signals.append("self_hosted=True")
            signals.append("uses_cloud_inference=False")
            signals.append("data_leaves_boundary=False")
            if config.has_cloud_storage:
                signals.append("has_cloud_storage=True (minor conflict)")
                confidence -= 0.15
            level = DeploymentLevel.L3_ON_PREM
            rationale = (
                "All inference runs on operator-owned infrastructure. "
                "Data does not leave the organisational boundary."
            )
            return self._build_result(level, confidence, rationale, signals)

        # L2_HYBRID — mix of cloud and local
        if config.uses_cloud_inference and config.uses_local_inference:
            signals.append("uses_cloud_inference=True")
            signals.append("uses_local_inference=True")
            if not config.data_leaves_boundary:
                signals.append("data_leaves_boundary=False")
                confidence -= 0.1  # Slight inconsistency
            level = DeploymentLevel.L2_HYBRID
            rationale = (
                "Agent uses both cloud and local inference paths. "
                "Sensitive workloads are processed locally."
            )
            return self._build_result(level, confidence, rationale, signals)

        # L3_ON_PREM — self-hosted with local inference (no cloud)
        if config.self_hosted and config.uses_local_inference and not config.uses_cloud_inference:
            signals.append("self_hosted=True")
            signals.append("uses_local_inference=True")
            signals.append("uses_cloud_inference=False")
            level = DeploymentLevel.L3_ON_PREM
            rationale = (
                "Agent runs local inference on self-hosted infrastructure "
                "without any cloud dependency."
            )
            return self._build_result(level, confidence, rationale, signals)

        # L1_CLOUD — default: cloud inference, data leaves boundary
        signals.append("uses_cloud_inference=True")
        if config.data_leaves_boundary:
            signals.append("data_leaves_boundary=True")
        if config.has_cloud_storage:
            signals.append("has_cloud_storage=True")
        level = DeploymentLevel.L1_CLOUD
        rationale = (
            "Agent relies on third-party cloud services for inference and/or "
            "storage. Data crosses the organisational boundary."
        )
        return self._build_result(level, confidence, rationale, signals)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_result(
        level: DeploymentLevel,
        confidence: float,
        rationale: str,
        signals: list[str],
    ) -> SovereigntyLevelResult:
        """Construct a :class:`SovereigntyLevelResult`.

        Clamps confidence to [0.0, 1.0].
        """
        clamped_confidence = max(0.0, min(1.0, confidence))
        return SovereigntyLevelResult(
            level=level,
            description=LEVEL_DESCRIPTIONS[level],
            requirements=LEVEL_REQUIREMENTS[level],
            confidence=clamped_confidence,
            rationale=rationale,
            config_signals=signals,
        )

    def get_level_description(self, level: DeploymentLevel) -> str:
        """Return the human-readable description for *level*.

        Parameters
        ----------
        level:
            A :class:`DeploymentLevel` enum member.

        Returns
        -------
        str
            Description string from :data:`LEVEL_DESCRIPTIONS`.
        """
        return LEVEL_DESCRIPTIONS[level]

    def get_level_requirements(self, level: DeploymentLevel) -> list[str]:
        """Return the capability requirements for *level*.

        Parameters
        ----------
        level:
            A :class:`DeploymentLevel` enum member.

        Returns
        -------
        list[str]
            Requirement tokens from :data:`LEVEL_REQUIREMENTS`.
        """
        return LEVEL_REQUIREMENTS[level]


__all__ = [
    "AgentConfig",
    "DeploymentLevel",
    "LEVEL_DESCRIPTIONS",
    "LEVEL_REQUIREMENTS",
    "SovereigntyClassifier",
    "SovereigntyLevelResult",
]
