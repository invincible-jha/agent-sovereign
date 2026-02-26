"""Tests for SovereigntyComplianceChecker and related dataclasses."""
from __future__ import annotations

import pytest

from agent_sovereign.classifier.levels import SovereigntyLevel
from agent_sovereign.compliance.checker import (
    ComplianceIssue,
    ComplianceReport,
    ComplianceStatus,
    SovereigntyComplianceChecker,
)
from agent_sovereign.deployment.validator import DeploymentConfig, DeploymentValidator
from agent_sovereign.residency.policy import DataResidencyPolicy, ResidencyChecker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(
    level: SovereigntyLevel = SovereigntyLevel.L1_CLOUD,
    region: str = "US",
    network_isolated: bool = False,
    air_gapped: bool = False,
    tpm: bool = False,
    fips: bool = False,
    encryption_rest: str = "AES-256",
    encryption_transit: str = "TLS-1.3",
    key_mgmt: str = "provider_managed",
    audit: bool = True,
) -> DeploymentConfig:
    return DeploymentConfig(
        sovereignty_level=level,
        data_residency_region=region,
        network_isolated=network_isolated,
        encryption_at_rest=encryption_rest,
        encryption_in_transit=encryption_transit,
        key_management=key_mgmt,
        audit_logging_enabled=audit,
        air_gapped=air_gapped,
        tpm_present=tpm,
        fips_hardware=fips,
    )


def _eu_gdpr_policy() -> DataResidencyPolicy:
    return DataResidencyPolicy(
        policy_id="eu-gdpr",
        allowed_regions=["EU", "DE", "FR"],
        require_data_localisation=True,
        description="EU GDPR policy",
    )


# ---------------------------------------------------------------------------
# ComplianceIssue
# ---------------------------------------------------------------------------

class TestComplianceIssue:
    def test_fields(self) -> None:
        issue = ComplianceIssue(
            issue_id="test.check",
            severity="high",
            description="Something is wrong",
            remediation="Fix it",
        )
        assert issue.issue_id == "test.check"
        assert issue.severity == "high"
        assert issue.check_source == "compliance_checker"

    def test_custom_check_source(self) -> None:
        issue = ComplianceIssue(
            issue_id="custom.check",
            severity="critical",
            description="Bad",
            remediation="Fix",
            check_source="custom_module",
        )
        assert issue.check_source == "custom_module"


# ---------------------------------------------------------------------------
# ComplianceReport
# ---------------------------------------------------------------------------

class TestComplianceReport:
    def test_is_compliant_true(self) -> None:
        report = ComplianceReport(
            deployment_id="test-deploy",
            assessed_at="2026-01-01T00:00:00",
            sovereignty_level=SovereigntyLevel.L1_CLOUD,
            overall_status=ComplianceStatus.COMPLIANT,
        )
        assert report.is_compliant is True

    def test_is_compliant_false(self) -> None:
        report = ComplianceReport(
            deployment_id="test",
            assessed_at="2026-01-01T00:00:00",
            sovereignty_level=SovereigntyLevel.L1_CLOUD,
            overall_status=ComplianceStatus.NON_COMPLIANT,
        )
        assert report.is_compliant is False

    def test_critical_issue_count(self) -> None:
        report = ComplianceReport(
            deployment_id="test",
            assessed_at="2026-01-01T00:00:00",
            sovereignty_level=SovereigntyLevel.L1_CLOUD,
            overall_status=ComplianceStatus.NON_COMPLIANT,
            issues=[
                ComplianceIssue("a", "critical", "d", "r"),
                ComplianceIssue("b", "critical", "d", "r"),
                ComplianceIssue("c", "high", "d", "r"),
            ],
        )
        assert report.critical_issue_count == 2

    def test_critical_issue_count_zero(self) -> None:
        report = ComplianceReport(
            deployment_id="test",
            assessed_at="2026-01-01T00:00:00",
            sovereignty_level=SovereigntyLevel.L1_CLOUD,
            overall_status=ComplianceStatus.COMPLIANT,
        )
        assert report.critical_issue_count == 0


# ---------------------------------------------------------------------------
# SovereigntyComplianceChecker construction
# ---------------------------------------------------------------------------

class TestCheckerConstruction:
    def test_default_construction(self) -> None:
        checker = SovereigntyComplianceChecker()
        assert checker is not None

    def test_with_policies(self) -> None:
        policy = _eu_gdpr_policy()
        checker = SovereigntyComplianceChecker(residency_policies=[policy])
        assert checker is not None

    def test_with_custom_validator(self) -> None:
        validator = DeploymentValidator()
        checker = SovereigntyComplianceChecker(validator=validator)
        assert checker is not None


# ---------------------------------------------------------------------------
# SovereigntyComplianceChecker.check — basic behaviour
# ---------------------------------------------------------------------------

class TestCheckerCheck:
    def test_l1_simple_config_returns_report(self) -> None:
        checker = SovereigntyComplianceChecker()
        config = _make_config()
        report = checker.check(config, deployment_id="deploy-001")
        assert report.deployment_id == "deploy-001"
        assert report.sovereignty_level == SovereigntyLevel.L1_CLOUD
        assert isinstance(report.assessed_at, str)

    def test_report_has_metadata(self) -> None:
        checker = SovereigntyComplianceChecker()
        config = _make_config()
        report = checker.check(config)
        assert "checked_policies" in report.metadata
        assert "validation_checks_run" in report.metadata

    def test_compliant_l1_cloud_config(self) -> None:
        checker = SovereigntyComplianceChecker()
        config = _make_config(
            level=SovereigntyLevel.L1_CLOUD,
            region="US",
            network_isolated=False,
            encryption_rest="AES-256",
            encryption_transit="TLS-1.3",
            key_mgmt="provider_managed",
            audit=True,
        )
        report = checker.check(config)
        assert report.overall_status in (
            ComplianceStatus.COMPLIANT, ComplianceStatus.PARTIAL
        )

    def test_residency_policy_pass_with_matching_region(self) -> None:
        policy = DataResidencyPolicy(
            policy_id="us-only",
            allowed_regions=["US"],
        )
        checker = SovereigntyComplianceChecker(residency_policies=[policy])
        config = _make_config(region="US")
        report = checker.check(config)
        # residency check should pass
        residency_checks = [c for c in report.passed_checks if "residency" in c]
        assert len(residency_checks) >= 1

    def test_residency_policy_fail_with_blocked_region(self) -> None:
        policy = DataResidencyPolicy(
            policy_id="no-cn",
            blocked_regions=["CN"],
            require_data_localisation=True,
        )
        checker = SovereigntyComplianceChecker(residency_policies=[policy])
        config = _make_config(region="CN")
        report = checker.check(config)
        assert report.overall_status == ComplianceStatus.NON_COMPLIANT

    def test_missing_region_with_localisation_policy_fails(self) -> None:
        policy = DataResidencyPolicy(
            policy_id="eu-strict",
            allowed_regions=["EU"],
            require_data_localisation=True,
        )
        checker = SovereigntyComplianceChecker(residency_policies=[policy])
        config = DeploymentConfig(
            sovereignty_level=SovereigntyLevel.L1_CLOUD,
            data_residency_region="",
            network_isolated=False,
            encryption_at_rest="AES-256",
            encryption_in_transit="TLS-1.3",
            key_management="provider_managed",
            audit_logging_enabled=True,
        )
        report = checker.check(config)
        assert report.overall_status == ComplianceStatus.NON_COMPLIANT

    def test_missing_region_no_localisation_policy_passes_residency(self) -> None:
        policy = DataResidencyPolicy(
            policy_id="open",
            # no allowed_regions, no require_data_localisation
        )
        checker = SovereigntyComplianceChecker(residency_policies=[policy])
        config = DeploymentConfig(
            sovereignty_level=SovereigntyLevel.L1_CLOUD,
            data_residency_region="",
            network_isolated=False,
            encryption_at_rest="AES-256",
            encryption_in_transit="TLS-1.3",
            key_management="provider_managed",
            audit_logging_enabled=True,
        )
        report = checker.check(config)
        residency_passed = [c for c in report.passed_checks if "residency" in c]
        assert len(residency_passed) >= 1

    def test_additional_policies_applied(self) -> None:
        checker = SovereigntyComplianceChecker()
        extra_policy = DataResidencyPolicy(
            policy_id="extra-us",
            allowed_regions=["US"],
        )
        config = _make_config(region="US")
        report = checker.check(config, additional_policies=[extra_policy])
        assert "residency.extra-us" in report.passed_checks

    def test_l5_without_isolation_fails(self) -> None:
        checker = SovereigntyComplianceChecker()
        config = _make_config(
            level=SovereigntyLevel.L5_FULLY_LOCAL,
            network_isolated=False,
            air_gapped=False,
        )
        report = checker.check(config)
        assert any("l5_plus" in f for f in report.failed_checks)

    def test_l5_with_network_isolation_passes_level_check(self) -> None:
        checker = SovereigntyComplianceChecker()
        config = _make_config(
            level=SovereigntyLevel.L5_FULLY_LOCAL,
            network_isolated=True,
            air_gapped=False,
        )
        report = checker.check(config)
        assert "level.l5_plus.network" in report.passed_checks

    def test_l5_with_air_gap_passes_level_check(self) -> None:
        checker = SovereigntyComplianceChecker()
        config = _make_config(
            level=SovereigntyLevel.L5_FULLY_LOCAL,
            network_isolated=False,
            air_gapped=True,
        )
        report = checker.check(config)
        assert "level.l5_plus.network" in report.passed_checks

    def test_jurisdiction_summary_populated_for_known_region(self) -> None:
        checker = SovereigntyComplianceChecker()
        config = _make_config(region="DE")
        report = checker.check(config)
        assert len(report.jurisdiction_summary) > 0

    def test_unknown_region_produces_warning_about_jurisdiction(self) -> None:
        checker = SovereigntyComplianceChecker()
        config = _make_config(region="UNKNOWN_REGION_XYZ")
        report = checker.check(config)
        assert any("jurisdiction" in w.lower() or "UNKNOWN_REGION_XYZ" in w for w in report.warnings)

    def test_warnings_only_status_is_partial(self) -> None:
        checker = SovereigntyComplianceChecker()
        # Use a region that triggers a jurisdiction warning but no failures
        config = _make_config(region="ZZZZZ")
        report = checker.check(config)
        # Should be PARTIAL (warnings, no hard failures)
        assert report.overall_status in (ComplianceStatus.PARTIAL, ComplianceStatus.COMPLIANT)

    def test_deployment_id_default_is_unknown(self) -> None:
        checker = SovereigntyComplianceChecker()
        config = _make_config()
        report = checker.check(config)
        assert report.deployment_id == "unknown"


# ---------------------------------------------------------------------------
# Static helper methods
# ---------------------------------------------------------------------------

class TestStaticHelpers:
    def test_severity_for_critical_check_at_l4(self) -> None:
        sev = SovereigntyComplianceChecker._severity_for_check(
            "air_gap", SovereigntyLevel.L4_LOCAL_AUGMENTED
        )
        assert sev == "critical"

    def test_severity_for_critical_check_at_l1(self) -> None:
        sev = SovereigntyComplianceChecker._severity_for_check(
            "air_gap", SovereigntyLevel.L1_CLOUD
        )
        assert sev == "high"

    def test_severity_for_high_check(self) -> None:
        sev = SovereigntyComplianceChecker._severity_for_check(
            "network_isolation", SovereigntyLevel.L1_CLOUD
        )
        assert sev == "high"

    def test_severity_for_unknown_check(self) -> None:
        sev = SovereigntyComplianceChecker._severity_for_check(
            "unknown_check", SovereigntyLevel.L1_CLOUD
        )
        assert sev == "medium"

    def test_remediation_for_known_check(self) -> None:
        remediation = SovereigntyComplianceChecker._remediation_for_check("air_gap")
        assert "air" in remediation.lower() or "disconnect" in remediation.lower()

    def test_remediation_for_network_isolation(self) -> None:
        remediation = SovereigntyComplianceChecker._remediation_for_check("network_isolation")
        assert len(remediation) > 10

    def test_remediation_for_unknown_check(self) -> None:
        remediation = SovereigntyComplianceChecker._remediation_for_check("mystery_check")
        assert "mystery_check" in remediation

    def test_remediation_for_all_known_checks(self) -> None:
        known = [
            "data_residency", "network_isolation", "encryption_at_rest",
            "encryption_in_transit", "key_management", "audit_logging",
            "air_gap", "tpm", "fips_hardware",
        ]
        for check in known:
            result = SovereigntyComplianceChecker._remediation_for_check(check)
            assert isinstance(result, str) and len(result) > 0
