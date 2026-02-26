"""Sovereignty level definitions.

Defines the SovereigntyLevel enum spanning L1_CLOUD through L7_AIRGAPPED,
along with human-readable descriptions and capability requirements for each
level.
"""
from __future__ import annotations

from enum import IntEnum


class SovereigntyLevel(IntEnum):
    """Sovereignty levels from least to most sovereign.

    Each level represents a progressively more restricted deployment posture.
    Higher numeric values indicate greater isolation and data control.
    """

    L1_CLOUD = 1
    """Standard cloud deployment. Multi-tenant SaaS, shared infrastructure.
    Suitable for public or low-sensitivity data."""

    L2_CLOUD_DEDICATED = 2
    """Dedicated cloud tenancy. Single-tenant cloud with logical isolation.
    Suitable for internal or lightly regulated data."""

    L3_HYBRID = 3
    """Hybrid deployment. Sensitive processing on-premises, public workloads
    in cloud. Compliant with HIPAA, SOX, FERPA baselines."""

    L4_LOCAL_AUGMENTED = 4
    """Local-primary with cloud augmentation. Inference and data processing
    happen on-premises; cloud used for model updates and telemetry only."""

    L5_FULLY_LOCAL = 5
    """Fully local deployment. No data egress to external services. All
    inference, storage, and processing remain on controlled infrastructure."""

    L6_CLASSIFIED = 6
    """Classified network deployment. Air-gap-adjacent environments, CUI,
    GDPR-maximum, or national-security-adjacent requirements."""

    L7_AIRGAPPED = 7
    """True air-gap. No network connectivity whatsoever. ITAR, SCI, or
    equivalent. Physical media transfer only for model updates."""


LEVEL_DESCRIPTIONS: dict[SovereigntyLevel, str] = {
    SovereigntyLevel.L1_CLOUD: (
        "Standard multi-tenant cloud. Data may reside on shared infrastructure "
        "with provider-managed encryption. Suitable for public or non-sensitive workloads."
    ),
    SovereigntyLevel.L2_CLOUD_DEDICATED: (
        "Dedicated single-tenant cloud environment with logical isolation. "
        "Appropriate for internal business data and lightly regulated workloads."
    ),
    SovereigntyLevel.L3_HYBRID: (
        "Hybrid architecture: sensitive compute and storage on-premises, "
        "non-sensitive workloads may use cloud services. Meets HIPAA, SOX, "
        "FERPA, and EU AI Act (standard risk) baselines."
    ),
    SovereigntyLevel.L4_LOCAL_AUGMENTED: (
        "Local-first deployment. All inference and PII/PHI processing remain "
        "on controlled infrastructure. Cloud used only for non-sensitive telemetry "
        "and model distribution updates."
    ),
    SovereigntyLevel.L5_FULLY_LOCAL: (
        "Fully local deployment with zero data egress. All pipeline components "
        "run on-premises or on approved edge devices. No external API calls."
    ),
    SovereigntyLevel.L6_CLASSIFIED: (
        "Classified or CUI-adjacent environment. Controlled unclassified information, "
        "GDPR maximum-restriction data, or national-security-adjacent workloads. "
        "Requires STIG-hardened OS and approved cryptography."
    ),
    SovereigntyLevel.L7_AIRGAPPED: (
        "True air-gap deployment. No network interfaces active. Physical media "
        "transfer required for all updates. Mandatory for ITAR-controlled technical "
        "data, SCI, and equivalent classified compartments."
    ),
}

CAPABILITY_REQUIREMENTS: dict[SovereigntyLevel, dict[str, str]] = {
    SovereigntyLevel.L1_CLOUD: {
        "network_access": "unrestricted",
        "data_storage": "cloud_provider_managed",
        "encryption_at_rest": "provider_default",
        "encryption_in_transit": "tls_1_2_plus",
        "model_hosting": "cloud_api",
        "audit_logging": "provider_managed",
        "key_management": "provider_managed",
        "update_mechanism": "automatic_cloud",
    },
    SovereigntyLevel.L2_CLOUD_DEDICATED: {
        "network_access": "restricted_to_tenant_vpc",
        "data_storage": "dedicated_cloud_volume",
        "encryption_at_rest": "customer_managed_keys",
        "encryption_in_transit": "tls_1_3",
        "model_hosting": "dedicated_cloud_endpoint",
        "audit_logging": "customer_accessible_logs",
        "key_management": "customer_managed_kms",
        "update_mechanism": "controlled_cloud",
    },
    SovereigntyLevel.L3_HYBRID: {
        "network_access": "on_prem_primary_cloud_secondary",
        "data_storage": "on_prem_primary",
        "encryption_at_rest": "customer_managed_hsm",
        "encryption_in_transit": "mtls",
        "model_hosting": "on_prem_with_cloud_fallback",
        "audit_logging": "on_prem_siem",
        "key_management": "on_prem_hsm",
        "update_mechanism": "approved_channels_only",
    },
    SovereigntyLevel.L4_LOCAL_AUGMENTED: {
        "network_access": "on_prem_only_limited_egress",
        "data_storage": "on_prem_only",
        "encryption_at_rest": "fips_140_2_l2",
        "encryption_in_transit": "mtls_internal_only",
        "model_hosting": "local_inference_server",
        "audit_logging": "local_siem_immutable",
        "key_management": "local_hsm",
        "update_mechanism": "manual_approved_packages",
    },
    SovereigntyLevel.L5_FULLY_LOCAL: {
        "network_access": "internal_only_no_egress",
        "data_storage": "local_encrypted_storage",
        "encryption_at_rest": "fips_140_2_l3",
        "encryption_in_transit": "internal_tls_only",
        "model_hosting": "fully_local_inference",
        "audit_logging": "local_immutable_logs",
        "key_management": "air_gapped_hsm",
        "update_mechanism": "signed_offline_packages",
    },
    SovereigntyLevel.L6_CLASSIFIED: {
        "network_access": "classified_network_only",
        "data_storage": "classified_storage_media",
        "encryption_at_rest": "fips_140_2_l3_nsa_approved",
        "encryption_in_transit": "classified_crypto",
        "model_hosting": "accredited_system_only",
        "audit_logging": "classified_audit_trail",
        "key_management": "nsa_type1_or_equivalent",
        "update_mechanism": "accredited_change_control",
    },
    SovereigntyLevel.L7_AIRGAPPED: {
        "network_access": "none",
        "data_storage": "airgapped_encrypted_media",
        "encryption_at_rest": "fips_140_2_l3_plus",
        "encryption_in_transit": "not_applicable",
        "model_hosting": "airgapped_local_only",
        "audit_logging": "physical_audit_trail",
        "key_management": "physical_key_ceremony",
        "update_mechanism": "physical_media_only",
    },
}


def get_level_description(level: SovereigntyLevel) -> str:
    """Return the human-readable description for a sovereignty level.

    Parameters
    ----------
    level:
        The sovereignty level to describe.

    Returns
    -------
    str
        A prose description of the level's characteristics.
    """
    return LEVEL_DESCRIPTIONS[level]


def get_capability_requirements(level: SovereigntyLevel) -> dict[str, str]:
    """Return the capability requirements dictionary for a sovereignty level.

    Parameters
    ----------
    level:
        The sovereignty level to query.

    Returns
    -------
    dict[str, str]
        A mapping of capability name to required value for the level.
    """
    return CAPABILITY_REQUIREMENTS[level].copy()


__all__ = [
    "SovereigntyLevel",
    "LEVEL_DESCRIPTIONS",
    "CAPABILITY_REQUIREMENTS",
    "get_level_description",
    "get_capability_requirements",
]
