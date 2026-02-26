"""Tests for DeploymentValidator, DeploymentPackager, DeploymentConfig."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from agent_sovereign.classifier.levels import SovereigntyLevel
from agent_sovereign.deployment.packager import (
    DeploymentManifest,
    DeploymentPackage,
    DeploymentPackager,
)
from agent_sovereign.deployment.validator import (
    DeploymentConfig,
    DeploymentValidator,
    ValidationStatus,
)
from agent_sovereign.residency.mapper import JurisdictionMapper, JurisdictionRequirements
from agent_sovereign.residency.policy import DataResidencyPolicy, ResidencyChecker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _config(
    level: SovereigntyLevel = SovereigntyLevel.L1_CLOUD,
    region: str = "US",
    network_isolated: bool = False,
    encryption_rest: str = "AES-256",
    encryption_transit: str = "TLS-1.3",
    key_mgmt: str = "provider_managed",
    audit: bool = True,
    air_gapped: bool = False,
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


# ---------------------------------------------------------------------------
# DeploymentValidator
# ---------------------------------------------------------------------------

class TestDeploymentValidator:
    def test_returns_list_of_results(self) -> None:
        validator = DeploymentValidator()
        config = _config()
        results = validator.validate(config)
        assert isinstance(results, list)
        assert len(results) == 9  # 9 checks

    def test_l1_basic_config_passes_data_residency(self) -> None:
        validator = DeploymentValidator()
        config = _config(level=SovereigntyLevel.L1_CLOUD, region="US")
        results = validator.validate(config)
        dr = next(r for r in results if r.check_id == "data_residency")
        assert dr.status == ValidationStatus.PASSED

    def test_l3_without_region_fails_data_residency(self) -> None:
        validator = DeploymentValidator()
        config = _config(level=SovereigntyLevel.L3_HYBRID, region="")
        results = validator.validate(config)
        dr = next(r for r in results if r.check_id == "data_residency")
        assert dr.status == ValidationStatus.FAILED

    def test_l3_with_region_passes_data_residency(self) -> None:
        validator = DeploymentValidator()
        config = _config(level=SovereigntyLevel.L3_HYBRID, region="EU")
        results = validator.validate(config)
        dr = next(r for r in results if r.check_id == "data_residency")
        assert dr.status == ValidationStatus.PASSED

    def test_network_isolation_required_but_missing_fails(self) -> None:
        validator = DeploymentValidator()
        # L4+ requires network isolation
        config = _config(
            level=SovereigntyLevel.L4_LOCAL_AUGMENTED,
            network_isolated=False,
        )
        results = validator.validate(config)
        ni = next(r for r in results if r.check_id == "network_isolation")
        assert ni.status == ValidationStatus.FAILED

    def test_overprovided_isolation_produces_warning(self) -> None:
        validator = DeploymentValidator()
        config = _config(level=SovereigntyLevel.L1_CLOUD, network_isolated=True)
        results = validator.validate(config)
        ni = next(r for r in results if r.check_id == "network_isolation")
        assert ni.status == ValidationStatus.WARNING

    def test_missing_encryption_at_rest_fails(self) -> None:
        validator = DeploymentValidator()
        config = _config(level=SovereigntyLevel.L1_CLOUD, encryption_rest="")
        results = validator.validate(config)
        er = next(r for r in results if r.check_id == "encryption_at_rest")
        assert er.status == ValidationStatus.FAILED

    def test_fips_required_but_missing_fails(self) -> None:
        validator = DeploymentValidator()
        # L5+ needs FIPS
        config = _config(
            level=SovereigntyLevel.L5_FULLY_LOCAL,
            region="US",
            encryption_rest="AES-256",  # no FIPS
            network_isolated=True,
        )
        results = validator.validate(config)
        er = next(r for r in results if r.check_id == "encryption_at_rest")
        assert er.status == ValidationStatus.FAILED

    def test_fips_encryption_passes(self) -> None:
        validator = DeploymentValidator()
        config = _config(
            level=SovereigntyLevel.L5_FULLY_LOCAL,
            region="US",
            encryption_rest="FIPS 140-2 AES-256",
            network_isolated=True,
        )
        results = validator.validate(config)
        er = next(r for r in results if r.check_id == "encryption_at_rest")
        assert er.status == ValidationStatus.PASSED

    def test_missing_encryption_in_transit_fails(self) -> None:
        validator = DeploymentValidator()
        config = _config(level=SovereigntyLevel.L2_CLOUD_DEDICATED, encryption_transit="")
        results = validator.validate(config)
        et = next(r for r in results if r.check_id == "encryption_in_transit")
        assert et.status == ValidationStatus.FAILED

    def test_air_gapped_skips_transit_encryption(self) -> None:
        validator = DeploymentValidator()
        config = _config(
            level=SovereigntyLevel.L7_AIRGAPPED,
            air_gapped=True,
            encryption_transit="",
            region="US",
        )
        results = validator.validate(config)
        et = next(r for r in results if r.check_id == "encryption_in_transit")
        assert et.status == ValidationStatus.SKIPPED

    def test_mtls_required_but_missing_fails(self) -> None:
        validator = DeploymentValidator()
        config = _config(
            level=SovereigntyLevel.L4_LOCAL_AUGMENTED,
            encryption_transit="TLS-1.3",  # not mTLS
            network_isolated=True,
            region="US",
        )
        results = validator.validate(config)
        et = next(r for r in results if r.check_id == "encryption_in_transit")
        assert et.status == ValidationStatus.FAILED

    def test_key_management_missing_fails(self) -> None:
        validator = DeploymentValidator()
        config = _config(level=SovereigntyLevel.L1_CLOUD, key_mgmt="")
        results = validator.validate(config)
        km = next(r for r in results if r.check_id == "key_management")
        assert km.status == ValidationStatus.FAILED

    def test_hsm_required_but_not_present_fails(self) -> None:
        validator = DeploymentValidator()
        config = _config(
            level=SovereigntyLevel.L4_LOCAL_AUGMENTED,
            network_isolated=True,
            region="US",
            key_mgmt="provider_managed",  # not HSM
        )
        results = validator.validate(config)
        km = next(r for r in results if r.check_id == "key_management")
        assert km.status == ValidationStatus.FAILED

    def test_hsm_key_management_passes(self) -> None:
        validator = DeploymentValidator()
        config = _config(
            level=SovereigntyLevel.L4_LOCAL_AUGMENTED,
            network_isolated=True,
            region="US",
            key_mgmt="local_hsm",
        )
        results = validator.validate(config)
        km = next(r for r in results if r.check_id == "key_management")
        assert km.status == ValidationStatus.PASSED

    def test_audit_logging_required_but_disabled_fails(self) -> None:
        validator = DeploymentValidator()
        config = _config(level=SovereigntyLevel.L3_HYBRID, region="US", audit=False)
        results = validator.validate(config)
        al = next(r for r in results if r.check_id == "audit_logging")
        assert al.status == ValidationStatus.FAILED

    def test_air_gap_required_but_missing_fails(self) -> None:
        validator = DeploymentValidator()
        config = _config(level=SovereigntyLevel.L7_AIRGAPPED, region="US", air_gapped=False)
        results = validator.validate(config)
        ag = next(r for r in results if r.check_id == "air_gap")
        assert ag.status == ValidationStatus.FAILED

    def test_tpm_required_but_missing_fails(self) -> None:
        validator = DeploymentValidator()
        config = _config(level=SovereigntyLevel.L5_FULLY_LOCAL, region="US", tpm=False)
        results = validator.validate(config)
        tpm = next(r for r in results if r.check_id == "tpm")
        assert tpm.status == ValidationStatus.FAILED

    def test_fips_hardware_required_but_missing_fails(self) -> None:
        validator = DeploymentValidator()
        config = _config(level=SovereigntyLevel.L6_CLASSIFIED, region="US", fips=False)
        results = validator.validate(config)
        fh = next(r for r in results if r.check_id == "fips_hardware")
        assert fh.status == ValidationStatus.FAILED


# ---------------------------------------------------------------------------
# DeploymentPackager
# ---------------------------------------------------------------------------

class TestDeploymentPackager:
    def test_package_with_explicit_files(self, tmp_path: Path) -> None:
        files = [tmp_path / "a.txt", tmp_path / "b.txt"]
        for f in files:
            f.write_text("content")
        packager = DeploymentPackager(SovereigntyLevel.L1_CLOUD)
        pkg = packager.package(explicit_files=files)
        assert len(pkg.files_list) == 2
        assert pkg.checksum is not None
        assert len(pkg.checksum) == 64

    def test_package_with_source_directory(self, tmp_path: Path) -> None:
        (tmp_path / "model.bin").write_text("weights")
        (tmp_path / "config.yaml").write_text("key: val")
        packager = DeploymentPackager(SovereigntyLevel.L3_HYBRID)
        pkg = packager.package(source_directory=tmp_path)
        assert len(pkg.files_list) == 2

    def test_package_raises_with_both_args(self, tmp_path: Path) -> None:
        packager = DeploymentPackager(SovereigntyLevel.L1_CLOUD)
        with pytest.raises(ValueError, match="not both"):
            packager.package(source_directory=tmp_path, explicit_files=[])

    def test_package_raises_with_no_args(self) -> None:
        packager = DeploymentPackager(SovereigntyLevel.L1_CLOUD)
        with pytest.raises(ValueError, match="One of"):
            packager.package()

    def test_package_raises_missing_directory(self, tmp_path: Path) -> None:
        packager = DeploymentPackager(SovereigntyLevel.L1_CLOUD)
        with pytest.raises(FileNotFoundError):
            packager.package(source_directory=tmp_path / "nonexistent")

    def test_manifest_has_correct_sovereignty_level(self, tmp_path: Path) -> None:
        packager = DeploymentPackager(SovereigntyLevel.L5_FULLY_LOCAL)
        (tmp_path / "file.txt").write_text("x")
        pkg = packager.package(source_directory=tmp_path)
        assert pkg.manifest.sovereignty_level == "L5_FULLY_LOCAL"

    def test_manifest_includes_metadata(self, tmp_path: Path) -> None:
        packager = DeploymentPackager(
            SovereigntyLevel.L1_CLOUD,
            metadata={"env": "prod"},
        )
        (tmp_path / "f.txt").write_text("x")
        pkg = packager.package(source_directory=tmp_path)
        assert pkg.manifest.metadata["env"] == "prod"

    def test_custom_package_id(self, tmp_path: Path) -> None:
        packager = DeploymentPackager(
            SovereigntyLevel.L1_CLOUD,
            package_id="custom-pkg-001",
        )
        (tmp_path / "f.txt").write_text("x")
        pkg = packager.package(source_directory=tmp_path)
        assert pkg.manifest.package_id == "custom-pkg-001"

    def test_auto_generated_package_id(self, tmp_path: Path) -> None:
        packager = DeploymentPackager(SovereigntyLevel.L1_CLOUD)
        (tmp_path / "f.txt").write_text("x")
        pkg = packager.package(source_directory=tmp_path)
        assert pkg.manifest.package_id.startswith("agsov-")

    def test_manifest_yaml_is_string(self, tmp_path: Path) -> None:
        packager = DeploymentPackager(SovereigntyLevel.L1_CLOUD)
        (tmp_path / "f.txt").write_text("x")
        pkg = packager.package(source_directory=tmp_path)
        assert isinstance(pkg.manifest_yaml, str)
        assert len(pkg.manifest_yaml) > 0

    def test_manifest_to_dict(self, tmp_path: Path) -> None:
        packager = DeploymentPackager(SovereigntyLevel.L1_CLOUD)
        (tmp_path / "f.txt").write_text("x")
        pkg = packager.package(source_directory=tmp_path)
        d = pkg.manifest.to_dict()
        assert "package_id" in d
        assert "sovereignty_level" in d
        assert "files" in d


# ---------------------------------------------------------------------------
# JurisdictionMapper
# ---------------------------------------------------------------------------

class TestJurisdictionMapper:
    def test_get_eu_requirements(self) -> None:
        mapper = JurisdictionMapper()
        req = mapper.get_requirements("EU")
        assert req.primary_regulation == "GDPR"

    def test_get_cn_requirements(self) -> None:
        mapper = JurisdictionMapper()
        req = mapper.get_requirements("CN")
        assert req.requires_data_localisation is True

    def test_unknown_jurisdiction_raises(self) -> None:
        mapper = JurisdictionMapper()
        with pytest.raises(KeyError):
            mapper.get_requirements("UNKNOWN")

    def test_register_custom_jurisdiction(self) -> None:
        mapper = JurisdictionMapper()
        custom = JurisdictionRequirements(
            jurisdiction="XX",
            primary_regulation="XX-Privacy-Act",
            requires_data_localisation=False,
            allows_cross_border_transfers=True,
            transfer_mechanisms=[],
            data_subject_rights=[],
            breach_notification_hours=48,
            supervisory_authority="XX Authority",
            special_category_data_rules="",
            agent_ai_specific_rules="",
            description="Test jurisdiction",
        )
        mapper.register(custom)
        assert mapper.get_requirements("XX").primary_regulation == "XX-Privacy-Act"

    def test_known_jurisdictions_sorted(self) -> None:
        mapper = JurisdictionMapper()
        jurisdictions = mapper.known_jurisdictions()
        assert jurisdictions == sorted(jurisdictions)

    def test_jurisdictions_requiring_localisation_includes_cn(self) -> None:
        mapper = JurisdictionMapper()
        local = mapper.jurisdictions_requiring_localisation()
        assert "CN" in local

    def test_jurisdictions_allowing_transfers_includes_eu(self) -> None:
        mapper = JurisdictionMapper()
        transfers = mapper.jurisdictions_allowing_transfers()
        assert "EU" in transfers

    def test_custom_jurisdictions_at_construction(self) -> None:
        custom = JurisdictionRequirements(
            jurisdiction="YY",
            primary_regulation="YY-Act",
            requires_data_localisation=True,
            allows_cross_border_transfers=False,
            transfer_mechanisms=[],
            data_subject_rights=[],
            breach_notification_hours=24,
            supervisory_authority="YY Auth",
            special_category_data_rules="",
            agent_ai_specific_rules="",
            description="",
        )
        mapper = JurisdictionMapper(custom_jurisdictions=[custom])
        assert "YY" in mapper.known_jurisdictions()


# ---------------------------------------------------------------------------
# ResidencyChecker
# ---------------------------------------------------------------------------

class TestResidencyChecker:
    def test_check_blocked_region_fails(self) -> None:
        checker = ResidencyChecker()
        policy = DataResidencyPolicy(
            policy_id="no-cn",
            blocked_regions=["CN"],
        )
        assert checker.check("CN", policy) is False

    def test_check_allowed_region_passes(self) -> None:
        checker = ResidencyChecker()
        policy = DataResidencyPolicy(
            policy_id="eu-only",
            allowed_regions=["EU", "DE"],
        )
        assert checker.check("EU", policy) is True
        assert checker.check("DE", policy) is True

    def test_check_not_in_allowed_regions_fails(self) -> None:
        checker = ResidencyChecker()
        policy = DataResidencyPolicy(
            policy_id="eu-only",
            allowed_regions=["EU", "DE"],
        )
        assert checker.check("US", policy) is False

    def test_check_allowed_jurisdictions(self) -> None:
        checker = ResidencyChecker()
        policy = DataResidencyPolicy(
            policy_id="eu-jurisdiction",
            allowed_jurisdictions=["EU"],
        )
        assert checker.check("DE", policy) is True  # DE maps to EU jurisdiction

    def test_check_disallowed_jurisdiction(self) -> None:
        checker = ResidencyChecker()
        policy = DataResidencyPolicy(
            policy_id="eu-jurisdiction",
            allowed_jurisdictions=["EU"],
        )
        assert checker.check("US", policy) is False

    def test_get_compliant_regions(self) -> None:
        checker = ResidencyChecker()
        policy = DataResidencyPolicy(
            policy_id="eu-only",
            allowed_regions=["EU", "DE", "FR"],
        )
        compliant = checker.get_compliant_regions(policy)
        assert "DE" in compliant or "EU" in compliant

    def test_get_jurisdiction_known_region(self) -> None:
        checker = ResidencyChecker()
        assert checker.get_jurisdiction("DE") == "EU"

    def test_get_jurisdiction_unknown_region(self) -> None:
        checker = ResidencyChecker()
        assert checker.get_jurisdiction("UNKNOWN") is None

    def test_known_regions_sorted(self) -> None:
        checker = ResidencyChecker()
        regions = checker.known_regions()
        assert regions == sorted(regions)

    def test_custom_region_jurisdiction_map(self) -> None:
        checker = ResidencyChecker(region_jurisdiction_map={"XX": "EU"})
        assert checker.get_jurisdiction("XX") == "EU"

    def test_country_in_allowed_region_group_passes(self) -> None:
        checker = ResidencyChecker()
        policy = DataResidencyPolicy(
            policy_id="eu-group",
            allowed_regions=["EU"],  # "EU" as group
        )
        # DE is in EU, so should pass via jurisdiction mapping
        result = checker.check("DE", policy)
        assert result is True
