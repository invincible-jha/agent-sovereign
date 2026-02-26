"""Sovereignty compliance checker.

Combines deployment configuration with data residency policies to produce
a structured ComplianceReport assessing whether a deployment satisfies
its stated sovereignty obligations.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum

from agent_sovereign.classifier.levels import SovereigntyLevel
from agent_sovereign.deployment.validator import DeploymentConfig, DeploymentValidator, ValidationStatus
from agent_sovereign.residency.mapper import JurisdictionMapper
from agent_sovereign.residency.policy import DataResidencyPolicy, ResidencyChecker


class ComplianceStatus(str, Enum):
    """Overall compliance status for a deployment."""

    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


@dataclass
class ComplianceIssue:
    """A single compliance issue discovered during checking.

    Attributes
    ----------
    issue_id:
        Short identifier for the issue type.
    severity:
        "critical", "high", "medium", or "low".
    description:
        Human-readable description of the issue.
    remediation:
        Suggested remediation action.
    check_source:
        Which checker module raised the issue.
    """

    issue_id: str
    severity: str
    description: str
    remediation: str
    check_source: str = "compliance_checker"


@dataclass
class ComplianceReport:
    """Full compliance report for a deployment.

    Attributes
    ----------
    deployment_id:
        Identifier for the deployment being assessed.
    assessed_at:
        ISO-8601 UTC timestamp of the assessment.
    sovereignty_level:
        The claimed sovereignty level of the deployment.
    overall_status:
        Aggregated compliance status.
    issues:
        List of individual compliance issues found.
    passed_checks:
        List of check IDs that passed.
    failed_checks:
        List of check IDs that failed.
    warnings:
        Advisory warnings that do not constitute failures.
    jurisdiction_summary:
        Summary of jurisdiction-specific findings.
    metadata:
        Additional context attached to this report.
    """

    deployment_id: str
    assessed_at: str
    sovereignty_level: SovereigntyLevel
    overall_status: ComplianceStatus
    issues: list[ComplianceIssue] = field(default_factory=list)
    passed_checks: list[str] = field(default_factory=list)
    failed_checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    jurisdiction_summary: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def is_compliant(self) -> bool:
        """Return True if the deployment is fully compliant."""
        return self.overall_status == ComplianceStatus.COMPLIANT

    @property
    def critical_issue_count(self) -> int:
        """Return the number of critical severity issues."""
        return sum(1 for issue in self.issues if issue.severity == "critical")


class SovereigntyComplianceChecker:
    """Checks deployments for compliance with sovereignty and residency policies.

    Combines DeploymentValidator checks with DataResidencyPolicy and
    JurisdictionMapper analysis to produce a unified ComplianceReport.

    Parameters
    ----------
    residency_policies:
        List of DataResidencyPolicy objects that the deployment must satisfy.
        All policies are evaluated; the strictest result is used.
    validator:
        Optional DeploymentValidator instance. A default validator is
        created if not provided.
    jurisdiction_mapper:
        Optional JurisdictionMapper for jurisdiction lookups. Built-in
        mapper is used if not provided.
    residency_checker:
        Optional ResidencyChecker for policy evaluation.
    """

    def __init__(
        self,
        residency_policies: list[DataResidencyPolicy] | None = None,
        validator: DeploymentValidator | None = None,
        jurisdiction_mapper: JurisdictionMapper | None = None,
        residency_checker: ResidencyChecker | None = None,
    ) -> None:
        self._policies = residency_policies or []
        self._validator = validator or DeploymentValidator()
        self._jurisdiction_mapper = jurisdiction_mapper or JurisdictionMapper()
        self._residency_checker = residency_checker or ResidencyChecker()

    def check(
        self,
        deployment: DeploymentConfig,
        deployment_id: str = "unknown",
        additional_policies: list[DataResidencyPolicy] | None = None,
    ) -> ComplianceReport:
        """Run all compliance checks and produce a ComplianceReport.

        Executes:
        1. DeploymentValidator checks (sovereignty template requirements).
        2. Data residency policy checks for each policy.
        3. Jurisdiction-specific analysis for the deployment's region.

        Parameters
        ----------
        deployment:
            The deployment configuration to assess.
        deployment_id:
            An identifier for the deployment in the report.
        additional_policies:
            Extra residency policies to apply in addition to those
            configured at construction.

        Returns
        -------
        ComplianceReport
            Full compliance assessment.
        """
        assessed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        issues: list[ComplianceIssue] = []
        passed_checks: list[str] = []
        failed_checks: list[str] = []
        warnings: list[str] = []
        jurisdiction_summary: dict[str, str] = {}

        # 1. Deployment template validation
        validation_results = self._validator.validate(deployment)
        for result in validation_results:
            check_id = f"deployment.{result.check_id}"
            if result.status == ValidationStatus.PASSED:
                passed_checks.append(check_id)
            elif result.status == ValidationStatus.FAILED:
                failed_checks.append(check_id)
                issues.append(ComplianceIssue(
                    issue_id=check_id,
                    severity=self._severity_for_check(result.check_id, deployment.sovereignty_level),
                    description=result.message,
                    remediation=self._remediation_for_check(result.check_id),
                    check_source="deployment_validator",
                ))
            elif result.status == ValidationStatus.WARNING:
                warnings.append(result.message)
            # SKIPPED results are ignored

        # 2. Residency policy checks
        all_policies = list(self._policies) + (additional_policies or [])
        for policy in all_policies:
            policy_check_id = f"residency.{policy.policy_id}"
            location = deployment.data_residency_region

            if not location:
                if policy.require_data_localisation or policy.allowed_regions:
                    failed_checks.append(policy_check_id)
                    issues.append(ComplianceIssue(
                        issue_id=policy_check_id,
                        severity="high",
                        description=(
                            f"Policy {policy.policy_id!r} requires a residency region, "
                            "but data_residency_region is not set in the deployment config."
                        ),
                        remediation=(
                            "Set data_residency_region in the DeploymentConfig to a "
                            "recognised region code."
                        ),
                        check_source="residency_checker",
                    ))
                else:
                    passed_checks.append(policy_check_id)
                continue

            is_ok = self._residency_checker.check(location, policy)
            if is_ok:
                passed_checks.append(policy_check_id)
            else:
                failed_checks.append(policy_check_id)
                issues.append(ComplianceIssue(
                    issue_id=policy_check_id,
                    severity="critical",
                    description=(
                        f"Deployment location {location!r} does not satisfy "
                        f"residency policy {policy.policy_id!r}. "
                        f"{policy.description}"
                    ),
                    remediation=(
                        f"Move the deployment to one of the compliant regions: "
                        + ", ".join(
                            self._residency_checker.get_compliant_regions(policy)[:10]
                        )
                    ),
                    check_source="residency_checker",
                ))

        # 3. Jurisdiction analysis
        location = deployment.data_residency_region
        if location:
            jurisdiction = self._residency_checker.get_jurisdiction(location)
            if jurisdiction:
                try:
                    req = self._jurisdiction_mapper.get_requirements(jurisdiction)
                    jurisdiction_summary[jurisdiction] = (
                        f"Primary regulation: {req.primary_regulation}. "
                        f"Data localisation required: {req.requires_data_localisation}. "
                        f"Breach notification: {req.breach_notification_hours}h."
                    )
                    if req.requires_data_localisation and not deployment.network_isolated:
                        issues.append(ComplianceIssue(
                            issue_id=f"jurisdiction.{jurisdiction}.localisation",
                            severity="critical",
                            description=(
                                f"Jurisdiction {jurisdiction!r} mandates data localisation "
                                f"({req.primary_regulation}), but the deployment is not "
                                "network-isolated."
                            ),
                            remediation=(
                                "Enable network isolation to prevent data from crossing "
                                "jurisdictional borders."
                            ),
                            check_source="jurisdiction_mapper",
                        ))
                        failed_checks.append(f"jurisdiction.{jurisdiction}.localisation")
                    else:
                        passed_checks.append(f"jurisdiction.{jurisdiction}.localisation")
                except KeyError:
                    warnings.append(
                        f"Jurisdiction {jurisdiction!r} for region {location!r} is not "
                        "in the JurisdictionMapper. Jurisdiction-specific checks skipped."
                    )
            else:
                warnings.append(
                    f"Region {location!r} is not mapped to a known jurisdiction. "
                    "Jurisdiction-specific checks were skipped."
                )

        # 4. Level-specific checks
        if deployment.sovereignty_level >= SovereigntyLevel.L5_FULLY_LOCAL:
            if not deployment.air_gapped and not deployment.network_isolated:
                issues.append(ComplianceIssue(
                    issue_id="level.l5_plus.network",
                    severity="critical",
                    description=(
                        f"Sovereignty level {deployment.sovereignty_level.name} requires "
                        "no internet egress, but the deployment is neither air-gapped "
                        "nor network-isolated."
                    ),
                    remediation=(
                        "Set air_gapped=True or network_isolated=True in the "
                        "DeploymentConfig."
                    ),
                    check_source="level_checker",
                ))
                failed_checks.append("level.l5_plus.network")
            else:
                passed_checks.append("level.l5_plus.network")

        # Determine overall status
        has_failures = len(failed_checks) > 0
        overall_status: ComplianceStatus
        if not has_failures and not warnings:
            overall_status = ComplianceStatus.COMPLIANT
        elif not has_failures:
            overall_status = ComplianceStatus.PARTIAL
        else:
            overall_status = ComplianceStatus.NON_COMPLIANT

        return ComplianceReport(
            deployment_id=deployment_id,
            assessed_at=assessed_at,
            sovereignty_level=deployment.sovereignty_level,
            overall_status=overall_status,
            issues=issues,
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            warnings=warnings,
            jurisdiction_summary=jurisdiction_summary,
            metadata={
                "checked_policies": str(len(all_policies)),
                "validation_checks_run": str(len(validation_results)),
            },
        )

    @staticmethod
    def _severity_for_check(check_id: str, level: SovereigntyLevel) -> str:
        """Map a validation check ID to a severity level.

        Parameters
        ----------
        check_id:
            The validation check identifier.
        level:
            The sovereignty level of the deployment.

        Returns
        -------
        str
            Severity string: "critical", "high", "medium", or "low".
        """
        critical_checks = {"air_gap", "fips_hardware", "tpm", "encryption_at_rest"}
        high_checks = {
            "network_isolation", "encryption_in_transit", "key_management", "audit_logging"
        }
        if check_id in critical_checks and level >= SovereigntyLevel.L4_LOCAL_AUGMENTED:
            return "critical"
        if check_id in critical_checks:
            return "high"
        if check_id in high_checks:
            return "high"
        return "medium"

    @staticmethod
    def _remediation_for_check(check_id: str) -> str:
        """Return a remediation suggestion for a failed check.

        Parameters
        ----------
        check_id:
            The validation check identifier.

        Returns
        -------
        str
            Suggested remediation.
        """
        remediations: dict[str, str] = {
            "data_residency": (
                "Ensure data_residency_region is set and matches the deployment's "
                "physical location. Enable local-only storage for L3+."
            ),
            "network_isolation": (
                "Enable network isolation by configuring firewall rules to block "
                "all external egress. Set network_isolated=True in DeploymentConfig."
            ),
            "encryption_at_rest": (
                "Configure FIPS 140-2 validated encryption for stored data. "
                "Use HSM-managed keys for L3+ deployments."
            ),
            "encryption_in_transit": (
                "Configure mutual TLS (mTLS) for all service-to-service communication. "
                "Disable TLS 1.0/1.1 and enforce TLS 1.3 where possible."
            ),
            "key_management": (
                "Deploy an on-premises HSM for key management. "
                "Ensure key rotation policies are in place."
            ),
            "audit_logging": (
                "Enable immutable audit logging. Configure a SIEM or write-once "
                "storage for audit log retention."
            ),
            "air_gap": (
                "Physically disconnect all network interfaces. "
                "Use physical media for all model and software updates."
            ),
            "tpm": (
                "Provision hardware with a Trusted Platform Module (TPM 2.0 or later). "
                "Enable TPM attestation in the OS configuration."
            ),
            "fips_hardware": (
                "Replace hardware with FIPS 140-2 validated equivalents. "
                "Verify FIPS mode is enabled in the OS cryptographic modules."
            ),
        }
        return remediations.get(
            check_id,
            f"Review the {check_id!r} requirement in the deployment template and "
            "update the deployment configuration accordingly.",
        )


__all__ = [
    "ComplianceIssue",
    "ComplianceReport",
    "ComplianceStatus",
    "SovereigntyComplianceChecker",
]
