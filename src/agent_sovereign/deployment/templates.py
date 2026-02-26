"""Deployment templates for each sovereignty level.

Provides DeploymentTemplate dataclasses describing compute, storage,
network, and security requirements, and a library of pre-built templates
for every SovereigntyLevel.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from agent_sovereign.classifier.levels import SovereigntyLevel


@dataclass(frozen=True)
class ComputeRequirements:
    """Hardware and compute requirements for a deployment."""

    min_cpu_cores: int
    min_memory_gb: int
    gpu_required: bool
    tpm_required: bool
    secure_enclave_required: bool
    fips_validated_hardware: bool


@dataclass(frozen=True)
class StorageRequirements:
    """Storage requirements for a deployment."""

    min_storage_gb: int
    encryption_standard: str
    local_only: bool
    immutable_audit_log: bool
    encrypted_backup_required: bool


@dataclass(frozen=True)
class NetworkConfig:
    """Network configuration requirements for a deployment."""

    allow_internet_egress: bool
    allow_cloud_api_calls: bool
    require_private_network: bool
    require_network_isolation: bool
    allow_telemetry_egress: bool
    vpn_required: bool
    air_gapped: bool


@dataclass(frozen=True)
class SecurityControls:
    """Security controls required for a deployment."""

    mfa_required: bool
    rbac_required: bool
    encryption_at_rest: str
    encryption_in_transit: str
    key_management: str
    audit_logging: str
    vulnerability_scanning: bool
    stig_hardening: bool
    physical_access_controls: bool


@dataclass(frozen=True)
class DeploymentTemplate:
    """Describes all requirements for deploying at a given sovereignty level.

    Attributes
    ----------
    name:
        Unique identifier for this template (e.g. "l1_cloud").
    sovereignty_level:
        The SovereigntyLevel this template targets.
    description:
        Human-readable description of this template's deployment posture.
    compute_requirements:
        Hardware and compute requirements.
    storage_requirements:
        Storage and persistence requirements.
    network_config:
        Network topology and connectivity requirements.
    security_controls:
        Security and access control requirements.
    supported_model_formats:
        Model file formats supported at this sovereignty level.
    update_mechanism:
        How model and software updates are delivered.
    """

    name: str
    sovereignty_level: SovereigntyLevel
    description: str
    compute_requirements: ComputeRequirements
    storage_requirements: StorageRequirements
    network_config: NetworkConfig
    security_controls: SecurityControls
    supported_model_formats: list[str] = field(default_factory=list)
    update_mechanism: str = "automatic_cloud"


# ---------------------------------------------------------------------------
# Built-in template definitions
# ---------------------------------------------------------------------------

_L1_CLOUD = DeploymentTemplate(
    name="l1_cloud",
    sovereignty_level=SovereigntyLevel.L1_CLOUD,
    description=(
        "Standard multi-tenant cloud deployment. Suitable for public or "
        "non-sensitive workloads with provider-managed infrastructure."
    ),
    compute_requirements=ComputeRequirements(
        min_cpu_cores=2,
        min_memory_gb=4,
        gpu_required=False,
        tpm_required=False,
        secure_enclave_required=False,
        fips_validated_hardware=False,
    ),
    storage_requirements=StorageRequirements(
        min_storage_gb=20,
        encryption_standard="AES-256-provider-managed",
        local_only=False,
        immutable_audit_log=False,
        encrypted_backup_required=False,
    ),
    network_config=NetworkConfig(
        allow_internet_egress=True,
        allow_cloud_api_calls=True,
        require_private_network=False,
        require_network_isolation=False,
        allow_telemetry_egress=True,
        vpn_required=False,
        air_gapped=False,
    ),
    security_controls=SecurityControls(
        mfa_required=False,
        rbac_required=False,
        encryption_at_rest="provider_default",
        encryption_in_transit="TLS 1.2+",
        key_management="provider_managed",
        audit_logging="provider_managed",
        vulnerability_scanning=False,
        stig_hardening=False,
        physical_access_controls=False,
    ),
    supported_model_formats=["onnx", "pytorch", "safetensors", "gguf"],
    update_mechanism="automatic_cloud",
)

_L2_HYBRID = DeploymentTemplate(
    name="l2_hybrid",
    sovereignty_level=SovereigntyLevel.L2_CLOUD_DEDICATED,
    description=(
        "Dedicated single-tenant cloud with logical isolation. Suitable for "
        "internal data and lightly regulated workloads."
    ),
    compute_requirements=ComputeRequirements(
        min_cpu_cores=4,
        min_memory_gb=8,
        gpu_required=False,
        tpm_required=False,
        secure_enclave_required=False,
        fips_validated_hardware=False,
    ),
    storage_requirements=StorageRequirements(
        min_storage_gb=50,
        encryption_standard="AES-256-customer-managed",
        local_only=False,
        immutable_audit_log=True,
        encrypted_backup_required=True,
    ),
    network_config=NetworkConfig(
        allow_internet_egress=True,
        allow_cloud_api_calls=True,
        require_private_network=True,
        require_network_isolation=False,
        allow_telemetry_egress=True,
        vpn_required=False,
        air_gapped=False,
    ),
    security_controls=SecurityControls(
        mfa_required=True,
        rbac_required=True,
        encryption_at_rest="AES-256-CMK",
        encryption_in_transit="TLS 1.3",
        key_management="customer_managed_kms",
        audit_logging="customer_accessible_logs",
        vulnerability_scanning=True,
        stig_hardening=False,
        physical_access_controls=False,
    ),
    supported_model_formats=["onnx", "pytorch", "safetensors", "gguf"],
    update_mechanism="controlled_cloud",
)

_L3_ON_PREMISE = DeploymentTemplate(
    name="l3_on_premise",
    sovereignty_level=SovereigntyLevel.L3_HYBRID,
    description=(
        "Hybrid deployment with sensitive compute on-premises and non-sensitive "
        "workloads optionally in the cloud. Meets HIPAA, SOX, FERPA baselines."
    ),
    compute_requirements=ComputeRequirements(
        min_cpu_cores=8,
        min_memory_gb=32,
        gpu_required=False,
        tpm_required=True,
        secure_enclave_required=False,
        fips_validated_hardware=False,
    ),
    storage_requirements=StorageRequirements(
        min_storage_gb=200,
        encryption_standard="AES-256-HSM",
        local_only=True,
        immutable_audit_log=True,
        encrypted_backup_required=True,
    ),
    network_config=NetworkConfig(
        allow_internet_egress=False,
        allow_cloud_api_calls=True,
        require_private_network=True,
        require_network_isolation=True,
        allow_telemetry_egress=False,
        vpn_required=True,
        air_gapped=False,
    ),
    security_controls=SecurityControls(
        mfa_required=True,
        rbac_required=True,
        encryption_at_rest="AES-256-HSM",
        encryption_in_transit="mTLS",
        key_management="on_prem_hsm",
        audit_logging="on_prem_siem",
        vulnerability_scanning=True,
        stig_hardening=False,
        physical_access_controls=True,
    ),
    supported_model_formats=["onnx", "safetensors", "gguf"],
    update_mechanism="approved_channels_only",
)

_L4_AIR_GAPPED = DeploymentTemplate(
    name="l4_air_gapped",
    sovereignty_level=SovereigntyLevel.L4_LOCAL_AUGMENTED,
    description=(
        "Local-primary deployment with limited controlled egress for model "
        "updates. All inference and PII/PHI processing remain on-premises."
    ),
    compute_requirements=ComputeRequirements(
        min_cpu_cores=16,
        min_memory_gb=64,
        gpu_required=True,
        tpm_required=True,
        secure_enclave_required=True,
        fips_validated_hardware=True,
    ),
    storage_requirements=StorageRequirements(
        min_storage_gb=500,
        encryption_standard="FIPS-140-2-L2",
        local_only=True,
        immutable_audit_log=True,
        encrypted_backup_required=True,
    ),
    network_config=NetworkConfig(
        allow_internet_egress=False,
        allow_cloud_api_calls=False,
        require_private_network=True,
        require_network_isolation=True,
        allow_telemetry_egress=False,
        vpn_required=False,
        air_gapped=True,
    ),
    security_controls=SecurityControls(
        mfa_required=True,
        rbac_required=True,
        encryption_at_rest="FIPS-140-2-L2",
        encryption_in_transit="mTLS-internal-only",
        key_management="local_hsm",
        audit_logging="local_siem_immutable",
        vulnerability_scanning=True,
        stig_hardening=True,
        physical_access_controls=True,
    ),
    supported_model_formats=["onnx", "gguf"],
    update_mechanism="manual_approved_packages",
)


class TemplateLibrary:
    """Library of all built-in deployment templates.

    Provides access to pre-built templates for each sovereignty level.
    Custom templates can be registered and override built-in entries.
    """

    def __init__(self) -> None:
        self._templates: dict[str, DeploymentTemplate] = {
            template.name: template
            for template in [_L1_CLOUD, _L2_HYBRID, _L3_ON_PREMISE, _L4_AIR_GAPPED]
        }
        # Also index by sovereignty level for level-based lookup
        self._by_level: dict[SovereigntyLevel, DeploymentTemplate] = {
            template.sovereignty_level: template
            for template in [_L1_CLOUD, _L2_HYBRID, _L3_ON_PREMISE, _L4_AIR_GAPPED]
        }

    def register(self, template: DeploymentTemplate) -> None:
        """Register a custom template, overriding any existing entry.

        Parameters
        ----------
        template:
            The DeploymentTemplate to register. If a template with the
            same name already exists, it will be overwritten.
        """
        self._templates[template.name] = template
        self._by_level[template.sovereignty_level] = template

    def get_by_name(self, name: str) -> DeploymentTemplate:
        """Return a template by its string name.

        Parameters
        ----------
        name:
            Template name such as "l1_cloud" or "l4_air_gapped".

        Returns
        -------
        DeploymentTemplate
            The matching template.

        Raises
        ------
        KeyError
            If no template is registered under that name.
        """
        if name not in self._templates:
            raise KeyError(
                f"Template {name!r} not found. "
                f"Available templates: {sorted(self._templates)}"
            )
        return self._templates[name]

    def get_by_level(self, level: SovereigntyLevel) -> DeploymentTemplate:
        """Return the template for a given sovereignty level.

        Parameters
        ----------
        level:
            The SovereigntyLevel to look up.

        Returns
        -------
        DeploymentTemplate
            The template for that level, or the nearest lower level if an
            exact match does not exist (e.g. for L5/L6/L7, returns L4).

        Raises
        ------
        KeyError
            If no template at or below the requested level exists.
        """
        if level in self._by_level:
            return self._by_level[level]
        # Fall back to the nearest lower-level template
        for candidate_level in sorted(self._by_level, reverse=True):
            if candidate_level <= level:
                return self._by_level[candidate_level]
        raise KeyError(f"No template found for level {level!r} or any lower level.")

    def list_templates(self) -> list[str]:
        """Return sorted list of all registered template names.

        Returns
        -------
        list[str]
            Template names in alphabetical order.
        """
        return sorted(self._templates)


_DEFAULT_LIBRARY = TemplateLibrary()


def get_template(level: SovereigntyLevel) -> DeploymentTemplate:
    """Return the deployment template for a given sovereignty level.

    Uses the default template library. For levels L5–L7 (which share the
    air-gapped posture), returns the L4 air-gapped template as the closest
    built-in match.

    Parameters
    ----------
    level:
        The SovereigntyLevel to look up.

    Returns
    -------
    DeploymentTemplate
        The deployment template for that level.
    """
    return _DEFAULT_LIBRARY.get_by_level(level)


__all__ = [
    "ComputeRequirements",
    "DeploymentTemplate",
    "NetworkConfig",
    "SecurityControls",
    "StorageRequirements",
    "TemplateLibrary",
    "get_template",
]
