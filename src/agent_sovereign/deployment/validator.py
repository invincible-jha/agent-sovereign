"""Deployment validator.

Validates that a deployment configuration satisfies the sovereignty
requirements for its target level. Checks data residency, network
isolation, and encryption controls.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from agent_sovereign.classifier.levels import SovereigntyLevel
from agent_sovereign.deployment.templates import DeploymentTemplate, get_template


class ValidationStatus(str, Enum):
    """Outcome of a single validation check."""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class ValidationResult:
    """Result of a single sovereignty validation check.

    Attributes
    ----------
    check_id:
        Short identifier for the check (e.g. "data_residency").
    status:
        Whether the check passed, failed, or produced a warning.
    message:
        Human-readable explanation of the outcome.
    requirement:
        The requirement value expected by the template.
    actual:
        The actual value found in the deployment configuration.
    """

    check_id: str
    status: ValidationStatus
    message: str
    requirement: str = ""
    actual: str = ""


@dataclass
class DeploymentConfig:
    """Description of an existing or planned deployment to validate.

    Attributes
    ----------
    sovereignty_level:
        The level at which this deployment claims to operate.
    data_residency_region:
        ISO or region code where data will reside (e.g. "EU", "US").
    network_isolated:
        Whether the deployment is network-isolated (no internet egress).
    encryption_at_rest:
        Encryption standard applied to stored data.
    encryption_in_transit:
        Encryption standard applied to data in transit.
    key_management:
        Key management approach (e.g. "provider_managed", "local_hsm").
    audit_logging_enabled:
        Whether audit logging is configured.
    air_gapped:
        Whether the deployment has no network interfaces active.
    tpm_present:
        Whether a Trusted Platform Module is present.
    fips_hardware:
        Whether FIPS 140-2 validated hardware is in use.
    additional_attributes:
        Any extra deployment attributes for custom validation rules.
    """

    sovereignty_level: SovereigntyLevel
    data_residency_region: str
    network_isolated: bool
    encryption_at_rest: str
    encryption_in_transit: str
    key_management: str
    audit_logging_enabled: bool
    air_gapped: bool = False
    tpm_present: bool = False
    fips_hardware: bool = False
    additional_attributes: dict[str, str] = field(default_factory=dict)


class DeploymentValidator:
    """Validates a deployment configuration against sovereignty requirements.

    Compares a DeploymentConfig against the DeploymentTemplate for the
    target SovereigntyLevel and returns a list of ValidationResult objects.

    Parameters
    ----------
    template:
        Optional explicit template to validate against. If omitted, the
        built-in template for the deployment's sovereignty level is used.
    """

    def __init__(self, template: DeploymentTemplate | None = None) -> None:
        self._explicit_template = template

    def validate(self, config: DeploymentConfig) -> list[ValidationResult]:
        """Validate a deployment configuration.

        Runs all applicable checks and returns a result per check. A
        deployment is considered compliant only when no result has
        status == ValidationStatus.FAILED.

        Parameters
        ----------
        config:
            The deployment configuration to validate.

        Returns
        -------
        list[ValidationResult]
            One result per validation check, in deterministic order.
        """
        template = (
            self._explicit_template
            if self._explicit_template is not None
            else get_template(config.sovereignty_level)
        )

        results: list[ValidationResult] = []

        results.append(self._check_data_residency(config, template))
        results.append(self._check_network_isolation(config, template))
        results.append(self._check_encryption_at_rest(config, template))
        results.append(self._check_encryption_in_transit(config, template))
        results.append(self._check_key_management(config, template))
        results.append(self._check_audit_logging(config, template))
        results.append(self._check_air_gap(config, template))
        results.append(self._check_tpm(config, template))
        results.append(self._check_fips_hardware(config, template))

        return results

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_data_residency(
        config: DeploymentConfig,
        template: DeploymentTemplate,
    ) -> ValidationResult:
        """Verify that data residency constraints are satisfied."""
        # For levels L3+ storage must be local-only (no cross-border egress)
        requires_local_storage = template.storage_requirements.local_only
        region_specified = bool(config.data_residency_region)

        if requires_local_storage and not region_specified:
            return ValidationResult(
                check_id="data_residency",
                status=ValidationStatus.FAILED,
                message=(
                    f"Template {template.name!r} requires local-only storage, but "
                    "data_residency_region is not specified in the deployment config."
                ),
                requirement="local_only with residency region specified",
                actual="no region specified",
            )
        if requires_local_storage:
            return ValidationResult(
                check_id="data_residency",
                status=ValidationStatus.PASSED,
                message=(
                    f"Data residency satisfied: local-only storage in region "
                    f"{config.data_residency_region!r}."
                ),
                requirement="local_only",
                actual=config.data_residency_region,
            )
        return ValidationResult(
            check_id="data_residency",
            status=ValidationStatus.PASSED,
            message="Data residency requirement does not mandate local-only storage at this level.",
            requirement="any",
            actual=config.data_residency_region or "unspecified",
        )

    @staticmethod
    def _check_network_isolation(
        config: DeploymentConfig,
        template: DeploymentTemplate,
    ) -> ValidationResult:
        """Verify network isolation meets template requirements."""
        required_isolated = template.network_config.require_network_isolation

        if required_isolated and not config.network_isolated:
            return ValidationResult(
                check_id="network_isolation",
                status=ValidationStatus.FAILED,
                message=(
                    f"Template {template.name!r} requires network isolation, "
                    "but the deployment is not network-isolated."
                ),
                requirement="network_isolated=True",
                actual="network_isolated=False",
            )
        if not required_isolated and config.network_isolated:
            return ValidationResult(
                check_id="network_isolation",
                status=ValidationStatus.WARNING,
                message=(
                    "Deployment is network-isolated but the template does not require it. "
                    "This is acceptable (over-provisioned isolation)."
                ),
                requirement="not required",
                actual="network_isolated=True",
            )
        return ValidationResult(
            check_id="network_isolation",
            status=ValidationStatus.PASSED,
            message="Network isolation requirements are satisfied.",
            requirement=f"require_network_isolation={required_isolated}",
            actual=f"network_isolated={config.network_isolated}",
        )

    @staticmethod
    def _check_encryption_at_rest(
        config: DeploymentConfig,
        template: DeploymentTemplate,
    ) -> ValidationResult:
        """Verify encryption-at-rest standard meets template requirements."""
        required = template.storage_requirements.encryption_standard
        actual = config.encryption_at_rest

        if not actual:
            return ValidationResult(
                check_id="encryption_at_rest",
                status=ValidationStatus.FAILED,
                message="Encryption at rest is not configured in the deployment.",
                requirement=required,
                actual="none",
            )
        # Check FIPS requirement for high levels
        requires_fips = "FIPS" in required
        has_fips = "FIPS" in actual.upper() or "fips" in actual.lower()
        if requires_fips and not has_fips:
            return ValidationResult(
                check_id="encryption_at_rest",
                status=ValidationStatus.FAILED,
                message=(
                    f"Template requires FIPS-validated encryption at rest ({required}), "
                    f"but deployment uses {actual!r}."
                ),
                requirement=required,
                actual=actual,
            )
        return ValidationResult(
            check_id="encryption_at_rest",
            status=ValidationStatus.PASSED,
            message=f"Encryption at rest is configured: {actual!r}.",
            requirement=required,
            actual=actual,
        )

    @staticmethod
    def _check_encryption_in_transit(
        config: DeploymentConfig,
        template: DeploymentTemplate,
    ) -> ValidationResult:
        """Verify encryption-in-transit meets template requirements."""
        required = template.security_controls.encryption_in_transit
        actual = config.encryption_in_transit

        if not actual:
            # Air-gapped deployments have no transit; not applicable
            if template.network_config.air_gapped:
                return ValidationResult(
                    check_id="encryption_in_transit",
                    status=ValidationStatus.SKIPPED,
                    message="Air-gapped deployment: transit encryption check not applicable.",
                    requirement="not_applicable",
                    actual="not_applicable",
                )
            return ValidationResult(
                check_id="encryption_in_transit",
                status=ValidationStatus.FAILED,
                message="Encryption in transit is not configured.",
                requirement=required,
                actual="none",
            )
        requires_mtls = "mtls" in required.lower() or "mTLS" in required
        has_mtls = "mtls" in actual.lower()
        if requires_mtls and not has_mtls:
            return ValidationResult(
                check_id="encryption_in_transit",
                status=ValidationStatus.FAILED,
                message=(
                    f"Template requires mTLS ({required!r}), but deployment uses {actual!r}."
                ),
                requirement=required,
                actual=actual,
            )
        return ValidationResult(
            check_id="encryption_in_transit",
            status=ValidationStatus.PASSED,
            message=f"Encryption in transit is configured: {actual!r}.",
            requirement=required,
            actual=actual,
        )

    @staticmethod
    def _check_key_management(
        config: DeploymentConfig,
        template: DeploymentTemplate,
    ) -> ValidationResult:
        """Verify key management approach meets template requirements."""
        required = template.security_controls.key_management
        actual = config.key_management

        if not actual:
            return ValidationResult(
                check_id="key_management",
                status=ValidationStatus.FAILED,
                message="Key management approach is not specified.",
                requirement=required,
                actual="unspecified",
            )
        # Provider-managed keys are insufficient for on-prem/HSM levels
        requires_hsm = "hsm" in required.lower()
        has_hsm = "hsm" in actual.lower()
        if requires_hsm and not has_hsm:
            return ValidationResult(
                check_id="key_management",
                status=ValidationStatus.FAILED,
                message=(
                    f"Template requires HSM-based key management ({required!r}), "
                    f"but deployment uses {actual!r}."
                ),
                requirement=required,
                actual=actual,
            )
        return ValidationResult(
            check_id="key_management",
            status=ValidationStatus.PASSED,
            message=f"Key management approach is acceptable: {actual!r}.",
            requirement=required,
            actual=actual,
        )

    @staticmethod
    def _check_audit_logging(
        config: DeploymentConfig,
        template: DeploymentTemplate,
    ) -> ValidationResult:
        """Verify audit logging is enabled where required."""
        requires_immutable = template.storage_requirements.immutable_audit_log

        if requires_immutable and not config.audit_logging_enabled:
            return ValidationResult(
                check_id="audit_logging",
                status=ValidationStatus.FAILED,
                message=(
                    f"Template {template.name!r} requires immutable audit logging, "
                    "but audit logging is disabled."
                ),
                requirement="audit_logging_enabled=True",
                actual="audit_logging_enabled=False",
            )
        return ValidationResult(
            check_id="audit_logging",
            status=ValidationStatus.PASSED,
            message=(
                "Audit logging requirements are satisfied."
                if config.audit_logging_enabled
                else "Audit logging not required at this level."
            ),
            requirement=f"immutable_required={requires_immutable}",
            actual=f"enabled={config.audit_logging_enabled}",
        )

    @staticmethod
    def _check_air_gap(
        config: DeploymentConfig,
        template: DeploymentTemplate,
    ) -> ValidationResult:
        """Verify air-gap status meets template requirements."""
        requires_air_gap = template.network_config.air_gapped

        if requires_air_gap and not config.air_gapped:
            return ValidationResult(
                check_id="air_gap",
                status=ValidationStatus.FAILED,
                message=(
                    f"Template {template.name!r} requires a true air-gap, "
                    "but the deployment has network interfaces active."
                ),
                requirement="air_gapped=True",
                actual="air_gapped=False",
            )
        return ValidationResult(
            check_id="air_gap",
            status=ValidationStatus.PASSED,
            message="Air-gap requirements are satisfied.",
            requirement=f"air_gapped={requires_air_gap}",
            actual=f"air_gapped={config.air_gapped}",
        )

    @staticmethod
    def _check_tpm(
        config: DeploymentConfig,
        template: DeploymentTemplate,
    ) -> ValidationResult:
        """Verify TPM presence where required by the template."""
        requires_tpm = template.compute_requirements.tpm_required

        if requires_tpm and not config.tpm_present:
            return ValidationResult(
                check_id="tpm",
                status=ValidationStatus.FAILED,
                message=(
                    f"Template {template.name!r} requires a TPM, "
                    "but none is reported in the deployment config."
                ),
                requirement="tpm_required=True",
                actual="tpm_present=False",
            )
        return ValidationResult(
            check_id="tpm",
            status=ValidationStatus.PASSED,
            message=(
                "TPM requirement satisfied."
                if requires_tpm
                else "TPM not required at this sovereignty level."
            ),
            requirement=f"tpm_required={requires_tpm}",
            actual=f"tpm_present={config.tpm_present}",
        )

    @staticmethod
    def _check_fips_hardware(
        config: DeploymentConfig,
        template: DeploymentTemplate,
    ) -> ValidationResult:
        """Verify FIPS-validated hardware where required."""
        requires_fips_hw = template.compute_requirements.fips_validated_hardware

        if requires_fips_hw and not config.fips_hardware:
            return ValidationResult(
                check_id="fips_hardware",
                status=ValidationStatus.FAILED,
                message=(
                    f"Template {template.name!r} requires FIPS-validated hardware, "
                    "but fips_hardware is not set in the deployment config."
                ),
                requirement="fips_validated_hardware=True",
                actual="fips_hardware=False",
            )
        return ValidationResult(
            check_id="fips_hardware",
            status=ValidationStatus.PASSED,
            message=(
                "FIPS hardware requirement satisfied."
                if requires_fips_hw
                else "FIPS-validated hardware not required at this sovereignty level."
            ),
            requirement=f"fips_validated_hardware={requires_fips_hw}",
            actual=f"fips_hardware={config.fips_hardware}",
        )


__all__ = [
    "DeploymentConfig",
    "DeploymentValidator",
    "ValidationResult",
    "ValidationStatus",
]
