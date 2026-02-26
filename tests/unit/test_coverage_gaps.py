"""Targeted tests for remaining coverage gaps.

Covers:
- deployment/templates.py: TemplateLibrary.register(), get_by_name() KeyError,
  get_by_level() fallback and KeyError, list_templates()
- compliance/checker.py: ValidationStatus.WARNING branch (lines 186-187),
  jurisdiction localisation check with network isolation (lines 268-269)
- edge/runtime.py: /proc/meminfo fallback path (lines 309-312)
- classifier/rules.py: _load_from_file path via Path object (line 150)
- cli/__init__.py: module-level import (line 7)
"""
from __future__ import annotations

import io
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from agent_sovereign.classifier.levels import SovereigntyLevel
from agent_sovereign.classifier.rules import ClassificationRule, ClassificationRules
from agent_sovereign.compliance.checker import (
    ComplianceStatus,
    SovereigntyComplianceChecker,
)
from agent_sovereign.deployment.templates import (
    ComputeRequirements,
    DeploymentTemplate,
    NetworkConfig,
    SecurityControls,
    StorageRequirements,
    TemplateLibrary,
    get_template,
)
from agent_sovereign.deployment.validator import DeploymentConfig, DeploymentValidator, ValidationResult, ValidationStatus
from agent_sovereign.edge.runtime import EdgeConfig, EdgeRuntime, QuantizationLevel
from agent_sovereign.residency.policy import DataResidencyPolicy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_deployment_config(
    level: SovereigntyLevel = SovereigntyLevel.L1_CLOUD,
    region: str = "US",
    network_isolated: bool = False,
    air_gapped: bool = False,
    encryption_rest: str = "AES-256",
    encryption_transit: str = "TLS-1.3",
    key_mgmt: str = "provider_managed",
    audit: bool = True,
    tpm: bool = False,
    fips: bool = False,
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


def _make_template(
    name: str = "custom_template",
    level: SovereigntyLevel = SovereigntyLevel.L1_CLOUD,
) -> DeploymentTemplate:
    return DeploymentTemplate(
        name=name,
        sovereignty_level=level,
        description="Custom template for testing",
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
            encryption_standard="AES-256",
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
            encryption_at_rest="AES-256",
            encryption_in_transit="TLS-1.3",
            key_management="provider_managed",
            audit_logging="provider_managed",
            vulnerability_scanning=False,
            stig_hardening=False,
            physical_access_controls=False,
        ),
        supported_model_formats=["onnx"],
        update_mechanism="automatic_cloud",
    )


# ---------------------------------------------------------------------------
# deployment/templates.py — TemplateLibrary
# ---------------------------------------------------------------------------


class TestTemplateLibraryRegister:
    """Covers lines 318-319: TemplateLibrary.register()."""

    def test_register_adds_template_by_name(self) -> None:
        library = TemplateLibrary()
        custom = _make_template(name="my_custom", level=SovereigntyLevel.L1_CLOUD)
        library.register(custom)
        retrieved = library.get_by_name("my_custom")
        assert retrieved is custom

    def test_register_overrides_existing_template(self) -> None:
        library = TemplateLibrary()
        original = _make_template(name="l1_cloud", level=SovereigntyLevel.L1_CLOUD)
        library.register(original)
        # Should now return our custom object
        retrieved = library.get_by_name("l1_cloud")
        assert retrieved is original

    def test_register_updates_by_level_index(self) -> None:
        library = TemplateLibrary()
        custom = _make_template(name="custom_l2", level=SovereigntyLevel.L2_CLOUD_DEDICATED)
        library.register(custom)
        retrieved = library.get_by_level(SovereigntyLevel.L2_CLOUD_DEDICATED)
        assert retrieved is custom


class TestTemplateLibraryGetByName:
    """Covers lines 339-344: get_by_name() KeyError branch."""

    def test_get_by_name_returns_known_template(self) -> None:
        library = TemplateLibrary()
        template = library.get_by_name("l1_cloud")
        assert template.name == "l1_cloud"

    def test_get_by_name_raises_key_error_for_unknown(self) -> None:
        library = TemplateLibrary()
        with pytest.raises(KeyError, match="not found"):
            library.get_by_name("nonexistent_template_xyz")

    def test_get_by_name_key_error_lists_available(self) -> None:
        library = TemplateLibrary()
        with pytest.raises(KeyError) as exc_info:
            library.get_by_name("does_not_exist")
        error_text = str(exc_info.value)
        assert "Available templates" in error_text


class TestTemplateLibraryGetByLevel:
    """Covers line 371: get_by_level() fallback for levels above L4."""

    def test_get_by_level_l5_falls_back_to_l4(self) -> None:
        library = TemplateLibrary()
        template = library.get_by_level(SovereigntyLevel.L5_FULLY_LOCAL)
        # L5 is not in the built-in library; should fall back to L4
        assert template.sovereignty_level == SovereigntyLevel.L4_LOCAL_AUGMENTED

    def test_get_by_level_l6_falls_back_to_l4(self) -> None:
        library = TemplateLibrary()
        template = library.get_by_level(SovereigntyLevel.L6_CLASSIFIED)
        assert template.sovereignty_level == SovereigntyLevel.L4_LOCAL_AUGMENTED

    def test_get_by_level_l7_falls_back_to_l4(self) -> None:
        library = TemplateLibrary()
        template = library.get_by_level(SovereigntyLevel.L7_AIRGAPPED)
        assert template.sovereignty_level == SovereigntyLevel.L4_LOCAL_AUGMENTED

    def test_get_by_level_raises_key_error_when_empty_library(self) -> None:
        library = TemplateLibrary()
        # Remove all templates by replacing the internal dicts
        library._templates.clear()
        library._by_level.clear()
        with pytest.raises(KeyError):
            library.get_by_level(SovereigntyLevel.L1_CLOUD)

    def test_get_by_level_exact_match_for_l1(self) -> None:
        library = TemplateLibrary()
        template = library.get_by_level(SovereigntyLevel.L1_CLOUD)
        assert template.sovereignty_level == SovereigntyLevel.L1_CLOUD


class TestTemplateLibraryListTemplates:
    """Covers line 381: list_templates()."""

    def test_list_templates_returns_sorted_names(self) -> None:
        library = TemplateLibrary()
        names = library.list_templates()
        assert names == sorted(names)
        assert "l1_cloud" in names
        assert "l4_air_gapped" in names

    def test_list_templates_includes_registered_custom(self) -> None:
        library = TemplateLibrary()
        library.register(_make_template(name="zzz_custom"))
        names = library.list_templates()
        assert "zzz_custom" in names

    def test_get_template_module_function_for_l5(self) -> None:
        template = get_template(SovereigntyLevel.L5_FULLY_LOCAL)
        assert template.sovereignty_level == SovereigntyLevel.L4_LOCAL_AUGMENTED


# ---------------------------------------------------------------------------
# compliance/checker.py — WARNING branch (lines 186-187)
# ---------------------------------------------------------------------------


class TestComplianceCheckerWarningBranch:
    """Covers lines 186-187: ValidationStatus.WARNING results are added to warnings."""

    def test_validation_warning_appended_to_warnings_list(self) -> None:
        """Inject a validator that returns a WARNING result to exercise the branch."""
        warning_result = ValidationResult(
            check_id="test_warning_check",
            status=ValidationStatus.WARNING,
            message="This is a validation warning",
            requirement="optional",
            actual="present",
        )

        mock_validator = MagicMock(spec=DeploymentValidator)
        mock_validator.validate.return_value = [warning_result]

        checker = SovereigntyComplianceChecker(validator=mock_validator)
        config = _make_deployment_config()
        report = checker.check(config, deployment_id="warn-test")

        assert "This is a validation warning" in report.warnings

    def test_warning_status_leads_to_partial_compliance(self) -> None:
        """A deployment with only warnings (no failures) should be PARTIAL."""
        warning_result = ValidationResult(
            check_id="advisory_check",
            status=ValidationStatus.WARNING,
            message="Advisory: consider upgrading encryption",
            requirement="recommended",
            actual="present",
        )

        mock_validator = MagicMock(spec=DeploymentValidator)
        mock_validator.validate.return_value = [warning_result]

        checker = SovereigntyComplianceChecker(validator=mock_validator)
        # Use empty region so no jurisdiction checks run
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
        assert report.overall_status == ComplianceStatus.PARTIAL
        assert len(report.warnings) >= 1


# ---------------------------------------------------------------------------
# compliance/checker.py — jurisdiction localisation passed (lines 268-269)
# ---------------------------------------------------------------------------


class TestComplianceCheckerJurisdictionLocalisationPassed:
    """Covers lines 268-269: jurisdiction localisation check passes when
    network_isolated=True or data localisation is not required."""

    def test_jurisdiction_localisation_passed_when_network_isolated(self) -> None:
        """DE jurisdiction requires data localisation; with network_isolated=True
        the check should pass (line 267 passed_checks.append)."""
        checker = SovereigntyComplianceChecker()
        config = _make_deployment_config(
            level=SovereigntyLevel.L3_HYBRID,
            region="DE",
            network_isolated=True,
            encryption_rest="AES-256-HSM",
            encryption_transit="mTLS",
            key_mgmt="on_prem_hsm",
            audit=True,
        )
        report = checker.check(config)
        localisation_passed = [
            c for c in report.passed_checks if "localisation" in c
        ]
        assert len(localisation_passed) >= 1

    def test_jurisdiction_no_localisation_requirement_passes(self) -> None:
        """US jurisdiction does not mandate data localisation; localisation
        check should pass without network isolation."""
        checker = SovereigntyComplianceChecker()
        config = _make_deployment_config(
            region="US",
            network_isolated=False,
        )
        report = checker.check(config)
        # The US jurisdiction check should end up in passed_checks
        localisation_passed = [
            c for c in report.passed_checks if "localisation" in c
        ]
        assert len(localisation_passed) >= 1


# ---------------------------------------------------------------------------
# edge/runtime.py — /proc/meminfo fallback (lines 309-312)
# ---------------------------------------------------------------------------


class TestEdgeRuntimeProcMeminfoFallback:
    """Covers lines 309-312: /proc/meminfo read path when psutil is absent."""

    def test_proc_meminfo_fallback_returns_correct_value(self) -> None:
        """When psutil is not available but /proc/meminfo is readable, the
        method should parse MemAvailable and return the value in MiB."""
        meminfo_content = (
            "MemTotal:       16384000 kB\n"
            "MemFree:         8192000 kB\n"
            "MemAvailable:    4096000 kB\n"
            "Buffers:          512000 kB\n"
        )
        # Make psutil import fail, then provide a fake /proc/meminfo
        with patch.dict("sys.modules", {"psutil": None}):
            with patch("builtins.open", mock_open(read_data=meminfo_content)):
                result = EdgeRuntime._detect_available_memory_mb()
        # 4096000 kB / 1024 = 4000 MiB
        assert result == 4000

    def test_proc_meminfo_iterates_lines_to_find_memavailable(self) -> None:
        """Ensure the line-iteration loop finds MemAvailable even when it is
        not the first line."""
        meminfo_content = (
            "MemTotal:        8192000 kB\n"
            "MemFree:         1024000 kB\n"
            "MemAvailable:    2048000 kB\n"
        )
        with patch.dict("sys.modules", {"psutil": None}):
            m = mock_open(read_data=meminfo_content)
            # mock_open's __iter__ needs patching to return lines properly
            m.return_value.__iter__ = lambda self: iter(meminfo_content.splitlines(keepends=True))
            with patch("builtins.open", m):
                result = EdgeRuntime._detect_available_memory_mb()
        assert result == 2000  # 2048000 kB / 1024

    def test_os_error_on_proc_meminfo_falls_back_to_512(self) -> None:
        """When both psutil and /proc/meminfo are unavailable, returns 512."""
        with patch.dict("sys.modules", {"psutil": None}):
            with patch("builtins.open", side_effect=OSError("no /proc")):
                result = EdgeRuntime._detect_available_memory_mb()
        assert result == 512


# ---------------------------------------------------------------------------
# classifier/rules.py — _load_from_file path (line 150)
# ---------------------------------------------------------------------------


class TestClassificationRulesFromFile:
    """Covers line 150: loading rules from a Path object."""

    def test_load_from_path_object(self, tmp_path: Path) -> None:
        yaml_content = """\
version: "1.0"
rules:
  - id: test_rule
    description: "A test rule"
    minimum_level: 3
    data_types: ["secret_data"]
"""
        rules_file = tmp_path / "rules.yaml"
        rules_file.write_text(yaml_content, encoding="utf-8")

        engine = ClassificationRules(yaml_source=rules_file)
        assert len(engine.rules) == 1
        assert engine.rules[0].rule_id == "test_rule"
        assert engine.rules[0].minimum_level == 3

    def test_load_from_path_object_evaluates_correctly(self, tmp_path: Path) -> None:
        yaml_content = """\
version: "1.0"
rules:
  - id: custom_financial
    description: "Custom financial rule"
    minimum_level: 4
    data_types: ["custom_pii"]
    regulations: ["CUSTOM_REG"]
"""
        rules_file = tmp_path / "custom_rules.yaml"
        rules_file.write_text(yaml_content, encoding="utf-8")

        engine = ClassificationRules(yaml_source=rules_file)
        result = engine.evaluate(
            data_types=["custom_pii"],
            regulations=["CUSTOM_REG"],
        )
        assert result.rule_driven_level == SovereigntyLevel.L4_LOCAL_AUGMENTED

    def test_load_from_string_file_path_that_exists(self, tmp_path: Path) -> None:
        """When yaml_source is a str pointing to an existing file, it should
        load from the file (the path.exists() branch in __init__)."""
        yaml_content = """\
version: "1.0"
rules:
  - id: str_path_rule
    description: "Loaded via string path"
    minimum_level: 2
"""
        rules_file = tmp_path / "str_path_rules.yaml"
        rules_file.write_text(yaml_content, encoding="utf-8")

        engine = ClassificationRules(yaml_source=str(rules_file))
        assert any(r.rule_id == "str_path_rule" for r in engine.rules)


# ---------------------------------------------------------------------------
# cli/__init__.py — module-level import (line 7)
# ---------------------------------------------------------------------------


class TestCliInitImport:
    """Covers cli/__init__.py line 7: the `from __future__ import annotations`
    statement is executed on module import."""

    def test_cli_package_importable(self) -> None:
        import importlib
        import agent_sovereign.cli as cli_pkg
        assert cli_pkg is not None

    def test_cli_main_importable_from_package(self) -> None:
        from agent_sovereign.cli import main  # noqa: F401 — import is the test
        assert main is not None

    def test_core_init_importable(self) -> None:
        import agent_sovereign.core as core_pkg
        assert core_pkg is not None
